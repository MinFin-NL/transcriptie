import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.jobs import JobStore
from app.main import create_app
from app.turns import Segment


class FakeTranscriber:
    def __init__(self):
        self.calls: list[tuple[str, str | None]] = []

    async def transcribe(self, path: Path, language: str | None) -> str:
        self.calls.append((path.name, language))
        return f"deel {len(self.calls)}"

    async def transcribe_diarized(self, path: Path, language: str | None, num_speakers: int | None):
        self.calls.append((path.name, language))
        self.num_speakers = num_speakers
        return [
            Segment(0.0, 2.0, "SPEAKER_01", "Goedemiddag."),
            Segment(2.0, 3.0, "SPEAKER_00", "Hallo."),
            Segment(3.0, 5.0, "SPEAKER_00", "Ik heb een vraag."),
        ]


class FakeDiarizer:
    def __init__(self, ok: bool = True):
        self.ok = ok
        self.num_speakers: int | None = None

    def available(self) -> bool:
        return self.ok

    async def diarize(self, wav: Path, num_speakers: int | None) -> list[Segment]:
        self.num_speakers = num_speakers
        return [
            Segment(0.0, 3.0, "B"),
            Segment(3.0, 3.3, "A"),
            Segment(3.4, 6.0, "B"),
            Segment(6.0, 10.0, "A"),
        ]


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


def make_settings(tmp_path, **kw) -> Settings:
    return Settings(
        transcribe_url="http://example.invalid/v1/audio/transcriptions",
        max_duration_seconds=30,
        chunk_seconds=8,
        split_window_seconds=4,
        static_dir=tmp_path / "dist",
        **kw,
    )


@pytest.fixture
def setup(tmp_path):
    settings = make_settings(tmp_path)
    fake = FakeTranscriber()
    store = JobStore(settings, fake, FakeDiarizer())
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


def test_local_speakers_diarize_then_transcribe_per_turn(setup):
    client, fake, store, tmp = setup
    mp3 = tone(tmp / "overleg.mp3", 10)
    res = client.post(
        "/api/v1/transcriptions",
        files={"file": ("overleg.mp3", mp3.read_bytes(), "audio/mpeg")},
        data={"speakers": "true", "numSpeakers": "2"},
    )
    assert res.status_code == 202
    body = wait_done(client, res.headers["Location"])
    assert body["status"] == "done", body
    assert store.diarizer.num_speakers == 2
    # Het tussenwerpsel van A (0,3 s) hoort bij de beurt van B: twee beurten.
    assert [name for name, _ in fake.calls] == ["beurt-0000.wav", "beurt-0001.wav"]
    assert body["speakers"] == [{"id": "S1"}, {"id": "S2"}]
    assert body["segments"] == [
        {"speaker": "S1", "start": 0.0, "end": 6.0, "text": "deel 1"},
        {"speaker": "S2", "start": 6.0, "end": 10.0, "text": "deel 2"},
    ]
    assert body["text"] == "deel 1\n\ndeel 2"
    assert not store.jobs[body["id"]].workdir.exists()


def test_service_speakers_send_whole_recording(tmp_path):
    settings = make_settings(tmp_path, diarization="service")
    fake = FakeTranscriber()
    with TestClient(create_app(settings, JobStore(settings, fake))) as client:
        assert client.get("/api/v1/features").json() == {"speakers": True}
        mp3 = tone(tmp_path / "gesprek.mp3", 20)
        res = client.post(
            "/api/v1/transcriptions",
            files={"file": ("gesprek.mp3", mp3.read_bytes(), "audio/mpeg")},
            data={"speakers": "true"},
        )
        body = wait_done(client, res.headers["Location"])
    assert body["status"] == "done", body
    # Eén aanvraag ondanks chunk_seconds=8: anders kloppen de labels niet.
    assert [name for name, _ in fake.calls] == ["audio.wav"]
    assert fake.num_speakers is None
    assert body["speakers"] == [{"id": "S1"}, {"id": "S2"}]
    assert body["segments"][1] == {
        "speaker": "S2",
        "start": 2.0,
        "end": 5.0,
        "text": "Hallo. Ik heb een vraag.",
    }


def test_without_speakers_no_segments(setup):
    client, _, _, tmp = setup
    mp3 = tone(tmp / "a.mp3", 4)
    res = client.post("/api/v1/transcriptions", files={"file": ("a.mp3", mp3.read_bytes(), "audio/mpeg")})
    body = wait_done(client, res.headers["Location"])
    assert body["status"] == "done"
    assert "segments" not in body


def test_invalid_speaker_count_is_422(setup):
    client, fake, _, tmp = setup
    mp3 = tone(tmp / "a.mp3", 4)
    res = client.post(
        "/api/v1/transcriptions",
        files={"file": ("a.mp3", mp3.read_bytes(), "audio/mpeg")},
        data={"speakers": "true", "numSpeakers": "veel"},
    )
    assert res.status_code == 422
    assert res.headers["content-type"] == "application/problem+json"
    assert fake.calls == []


def test_speakers_unavailable(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore(settings, FakeTranscriber(), FakeDiarizer(ok=False))
    with TestClient(create_app(settings, store)) as client:
        assert client.get("/api/v1/features").json() == {"speakers": False}
        mp3 = tone(tmp_path / "a.mp3", 4)
        res = client.post(
            "/api/v1/transcriptions",
            files={"file": ("a.mp3", mp3.read_bytes(), "audio/mpeg")},
            data={"speakers": "true"},
        )
    assert res.status_code == 422


def test_diarization_off(tmp_path):
    settings = make_settings(tmp_path, diarization="off")
    with TestClient(create_app(settings, JobStore(settings, FakeTranscriber(), FakeDiarizer()))) as client:
        assert client.get("/api/v1/features").json() == {"speakers": False}


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
