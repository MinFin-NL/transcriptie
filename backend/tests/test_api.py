import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.jobs import JobStore
from app.main import create_app


class FakeTranscriber:
    def __init__(self):
        self.calls: list[tuple[str, str | None]] = []

    async def transcribe(self, path: Path, language: str | None) -> str:
        self.calls.append((path.name, language))
        return f"deel {len(self.calls)}"


def tone(path: Path, seconds: int) -> Path:
    # Toon, stilte, toon: zo vindt silencedetect een knippunt.
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-af",
            f"volume=enable='between(t,{seconds / 2 - 1},{seconds / 2})':volume=0",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "32k",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
def setup(tmp_path):
    settings = Settings(
        transcribe_url="http://example.invalid/v1/audio/transcriptions",
        max_duration_seconds=30,
        chunk_seconds=8,
        split_window_seconds=4,
        static_dir=tmp_path / "dist",
    )
    fake = FakeTranscriber()
    store = JobStore(settings, fake)
    with TestClient(create_app(settings, store)) as client:
        yield client, fake, store, tmp_path


def wait_done(client, location):
    for _ in range(100):
        body = client.get(location).json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("taak werd niet klaar")


def test_transcribes_in_chunks(setup):
    client, fake, store, tmp = setup
    mp3 = tone(tmp / "overleg.mp3", 20)
    res = client.post(
        "/api/v1/transcriptions",
        files={"file": ("overleg.mp3", mp3.read_bytes(), "audio/mpeg")},
        data={"language": "nl"},
    )
    assert res.status_code == 202
    assert res.headers["API-Version"]
    body = wait_done(client, res.headers["Location"])
    assert body["status"] == "done", body
    assert body["progress"]["total"] == 3
    assert body["progress"]["completed"] == 3
    assert body["text"] == "deel 1\n\ndeel 2\n\ndeel 3"
    assert all(lang == "nl" for _, lang in fake.calls)
    # Na afloop staat er geen audio meer op schijf.
    job = store.jobs[body["id"]]
    assert not job.workdir.exists()


def test_too_long_is_rejected_before_processing(setup):
    client, fake, _, tmp = setup
    mp3 = tone(tmp / "lang.mp3", 40)
    res = client.post("/api/v1/transcriptions", files={"file": ("lang.mp3", mp3.read_bytes(), "audio/mpeg")})
    assert res.status_code == 422
    assert res.headers["content-type"] == "application/problem+json"
    assert "maximum" in res.json()["detail"]
    assert fake.calls == []


def test_not_audio_is_rejected(setup):
    client, _, _, _ = setup
    res = client.post("/api/v1/transcriptions", files={"file": ("notities.txt", b"hallo", "text/plain")})
    assert res.status_code == 415
    assert res.json()["title"] == "Geen bruikbare audio"


def test_too_large_is_rejected(tmp_path):
    settings = Settings(max_upload_bytes=1024, static_dir=tmp_path)
    with TestClient(create_app(settings, JobStore(settings, FakeTranscriber()))) as client:
        res = client.post("/api/v1/transcriptions", files={"file": ("a.mp3", b"x" * 5000, "audio/mpeg")})
    assert res.status_code == 413


def test_unknown_job_is_404_problem(setup):
    client, _, _, _ = setup
    res = client.get("/api/v1/transcriptions/bestaat-niet")
    assert res.status_code == 404
    assert res.headers["content-type"] == "application/problem+json"


def test_delete_removes_the_job(setup):
    client, _, _, tmp = setup
    mp3 = tone(tmp / "a.mp3", 4)
    res = client.post("/api/v1/transcriptions", files={"file": ("a.mp3", mp3.read_bytes(), "audio/mpeg")})
    location = res.headers["Location"]
    assert client.delete(location).status_code == 204
    assert client.get(location).status_code == 404


def test_security_headers_and_spa_fallback(setup):
    client, _, _, tmp = setup
    dist = tmp / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>t</title>")
    res = client.get("/een/route")
    assert res.status_code == 200
    assert "default-src 'self'" in res.headers["Content-Security-Policy"]
    assert res.headers["Permissions-Policy"].startswith("microphone=(self)")
    # Geen pad buiten dist/.
    assert client.get("/../pyproject.toml").text.startswith("<!doctype html>")


def test_auth_header_bearer_by_default():
    assert Settings(api_key="abc").auth_headers() == {"Authorization": "Bearer abc"}
    assert Settings(api_key="abc", api_key_header="api-key").auth_headers() == {"api-key": "abc"}
    assert Settings(api_key="").auth_headers() == {}
