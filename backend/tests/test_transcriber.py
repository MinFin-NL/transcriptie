import httpx
import pytest

from app.config import Settings
from app.transcriber import Transcriber, TranscriberError


def make(handler, **kw):
    settings = Settings(transcribe_url="http://svc/v1/audio/transcriptions", transcribe_model="voxtral", **kw)
    return Transcriber(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.fixture
def wav(tmp_path):
    p = tmp_path / "deel-000.wav"
    p.write_bytes(b"RIFF....")
    return p


async def test_sends_multipart_with_model_and_language(wav):
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers.get("authorization")
        seen["body"] = req.content
        return httpx.Response(200, json={"text": " Goedemorgen. "})

    t = make(handler, api_key="geheim")
    assert await t.transcribe(wav, "nl") == "Goedemorgen."
    assert seen["auth"] == "Bearer geheim"
    assert b'name="model"\r\n\r\nvoxtral' in seen["body"]
    assert b'name="language"\r\n\r\nnl' in seen["body"]
    assert b'name="file"; filename="deel-000.wav"' in seen["body"]


async def test_json_body_without_json_content_type(wav):
    # Zo antwoordt Ollama: JSON, maar als text/plain.
    t = make(lambda req: httpx.Response(200, text='{"text":"Hallo"}', headers={"content-type": "text/plain"}))
    assert await t.transcribe(wav, None) == "Hallo"


async def test_plain_text_response(wav):
    t = make(lambda req: httpx.Response(200, text="Gewoon tekst\n"))
    assert await t.transcribe(wav, None) == "Gewoon tekst"


async def test_retries_when_busy(wav, monkeypatch):
    monkeypatch.setattr("app.transcriber.asyncio.sleep", _no_sleep)
    calls = iter([httpx.Response(429), httpx.Response(200, json={"text": "ok"})])
    t = make(lambda req: next(calls))
    assert await t.transcribe(wav, None) == "ok"


async def test_auth_error_is_readable(wav):
    t = make(lambda req: httpx.Response(401, json={"error": "nope"}))
    with pytest.raises(TranscriberError, match="weigert"):
        await t.transcribe(wav, None)


async def _no_sleep(_):
    return None
