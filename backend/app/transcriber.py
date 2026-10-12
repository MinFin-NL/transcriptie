"""De koppeling met de transcriptiedienst: de enige plek die weet hoe die praat.

In productie is dat vlam-api van vlam.ai (SSC-ICT); URL en sleutel komen uit de
secrets. vlam-api en Ollama (waarmee we lokaal Voxtral draaien) spreken
allebei het OpenAI-formaat van `/audio/transcriptions`: een multipart-POST met
`file`, `model` en optioneel `language`, en als antwoord `{"text": "..."}` (of
platte tekst).
Spreekt de dienst in Azure iets anders, dan verandert alleen dit bestand; de
rest van de app ziet alleen `transcribe(pad, taal) -> tekst`.

Met sprekers (DIARIZATION=service) vragen we `response_format=diarized_json`,
zoals vlam-api dat biedt (OpenAI-formaat, model `vlam-transcribe-prepaid`):
het antwoord heeft `segments` met per stuk `start`, `end`, `text` en `speaker`.
Dat wordt `transcribe_diarized(pad, taal, aantal) -> [Segment]`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx

from .config import Settings
from .turns import Segment

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
ATTEMPTS = 3


class TranscriberError(Exception):
    """Een fout met een tekst die zo voor de gebruiker te lezen is."""


class Transcriber:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.chunk_timeout_seconds, connect=10)
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(self, path: Path, language: str | None) -> str:
        return _text(await self._post(path, self._data(language, "json")))

    async def transcribe_diarized(
        self, path: Path, language: str | None, num_speakers: int | None
    ) -> list[Segment]:
        data = self._data(language, "diarized_json")
        if num_speakers:
            data["num_speakers"] = str(num_speakers)
        timeout = httpx.Timeout(self.settings.diarize_timeout_seconds, connect=10)
        return _segments(await self._post(path, data, timeout))

    def _data(self, language: str | None, response_format: str) -> dict[str, str]:
        data = {
            "model": self.settings.transcribe_model,
            "response_format": response_format,
            "temperature": "0",
        }
        if language:
            data["language"] = language
        return data

    async def _post(
        self, path: Path, data: dict[str, str], timeout: httpx.Timeout | None = None
    ) -> httpx.Response:
        s = self.settings
        for attempt in range(1, ATTEMPTS + 1):
            try:
                with path.open("rb") as fh:
                    res = await self._client.post(
                        s.transcribe_url,
                        headers=s.auth_headers(),
                        data=data,
                        files={"file": (path.name, fh, "audio/wav")},
                        **({"timeout": timeout} if timeout else {}),
                    )
            except httpx.TimeoutException as exc:
                raise TranscriberError("De transcriptiedienst reageerde niet op tijd.") from exc
            except httpx.HTTPError as exc:
                if attempt < ATTEMPTS:
                    await asyncio.sleep(2**attempt)
                    continue
                raise TranscriberError("De transcriptiedienst is niet bereikbaar.") from exc

            if res.status_code in RETRY_STATUS and attempt < ATTEMPTS:
                log.warning("transcriptiedienst gaf %s, poging %s", res.status_code, attempt)
                await asyncio.sleep(2**attempt)
                continue
            if res.status_code >= 400:
                # De body kan van alles bevatten; alleen de status in het log.
                log.error("transcriptiedienst gaf %s", res.status_code)
                raise TranscriberError(_message(res.status_code))
            return res

        raise TranscriberError("De transcriptiedienst is niet beschikbaar.")


def _text(res: httpx.Response) -> str:
    # Niet op de content-type vertrouwen: Ollama stuurt JSON als text/plain.
    body = res.text.strip()
    if "application/json" in res.headers.get("content-type", "") or body.startswith("{"):
        try:
            text = json.loads(body).get("text")
        except (ValueError, AttributeError) as exc:
            raise TranscriberError("De transcriptiedienst gaf een onverwacht antwoord.") from exc
        if not isinstance(text, str):
            raise TranscriberError("De transcriptiedienst gaf een onverwacht antwoord.")
        return text.strip()
    return body


def _segments(res: httpx.Response) -> list[Segment]:
    unexpected = "De transcriptiedienst gaf een onverwacht antwoord."
    try:
        raw = json.loads(res.text).get("segments")
    except (ValueError, AttributeError) as exc:
        raise TranscriberError(unexpected) from exc
    if not isinstance(raw, list):
        # Bijvoorbeeld Ollama, dat diarized_json negeert en alleen tekst geeft.
        raise TranscriberError(
            "De transcriptiedienst levert geen sprekers. Zet sprekerherkenning uit of neem contact op "
            "met de beheerder."
        )
    segments: list[Segment] = []
    try:
        for item in raw:
            segments.append(
                Segment(
                    start=float(item["start"]),
                    end=float(item["end"]),
                    speaker=str(item.get("speaker") or "?"),
                    text=str(item.get("text") or "").strip(),
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise TranscriberError(unexpected) from exc
    return segments


def _message(status: int) -> str:
    if status in (401, 403):
        return "De transcriptiedienst weigert de aanvraag. Neem contact op met de beheerder."
    if status == 404:
        return "Het transcriptiemodel is niet gevonden. Neem contact op met de beheerder."
    if status == 413:
        return "Een stuk audio was te groot voor de transcriptiedienst."
    if status == 429:
        return "De transcriptiedienst is te druk. Probeer het later opnieuw."
    return f"De transcriptiedienst gaf een fout ({status})."
