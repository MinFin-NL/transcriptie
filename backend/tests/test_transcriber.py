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


# Zo antwoordt vlam-api met response_format=diarized_json.
DIARIZED = {
    "text": "Goedemiddag, u spreekt met de servicedesk. Hallo, ik heb een vraag.",
    "usage": {"type": "duration", "seconds": 12},
    "segments": [
        {
            "type": "transcript.text.segment",
            "id": "seg_0",
            "start": 0.031,
            "end": 5.212,
            "text": "Goedemiddag, u spreekt met de servicedesk.",
            "speaker": "SPEAKER_01",
        },
        {
            "type": "transcript.text.segment",
            "id": "seg_1",
            "start": 5.212,
            "end": 8.587,
            "text": " Hallo, ik heb een vraag. ",
            "speaker": "SPEAKER_00",
        },
    ],
}


async def test_diarized_sends_format_and_speaker_count(wav):
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = req.content
        return httpx.Response(200, json=DIARIZED)

    segments = await make(handler).transcribe_diarized(wav, "nl", 2)
    assert b'name="response_format"\r\n\r\ndiarized_json' in seen["body"]
    assert b'name="num_speakers"\r\n\r\n2' in seen["body"]
    assert [(s.speaker, s.start, s.text) for s in segments] == [
        ("SPEAKER_01", 0.031, "Goedemiddag, u spreekt met de servicedesk."),
        ("SPEAKER_00", 5.212, "Hallo, ik heb een vraag."),
    ]


async def test_diarized_without_count_sends_no_hint(wav):
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = req.content
        return httpx.Response(200, json=DIARIZED)

    await make(handler).transcribe_diarized(wav, None, None)
    assert b"num_speakers" not in seen["body"]


async def test_diarized_from_service_without_speakers_is_readable(wav):
    # Ollama negeert diarized_json en geeft alleen tekst.
    t = make(lambda req: httpx.Response(200, json={"text": "Hallo"}))
    with pytest.raises(TranscriberError, match="geen sprekers"):
        await t.transcribe_diarized(wav, None, None)
