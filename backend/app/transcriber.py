"""De koppeling met de transcriptiedienst: de enige plek die weet hoe die praat.

In productie is dat vlam-api van vlam.ai (SSC-ICT); URL en sleutel komen uit de
secrets. Het exacte formaat van vlam-api's `transcribe` is nog niet bekend (zie
docs/vlam-ai.md). Deze adapter spreekt nu het formaat van Ollama's transcriptie-endpoint,
waarmee we lokaal Voxtral draaien: een multipart-POST met `file`, `model` en
optioneel `language`, en als antwoord `{"text": "..."}` (of platte tekst).
Spreekt de dienst in Azure iets anders, dan verandert alleen dit bestand; de
rest van de app ziet alleen `transcribe(pad, taal) -> tekst`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx

from .config import Settings

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
        s = self.settings
        data = {"model": s.transcribe_model, "response_format": "json", "temperature": "0"}
        if language:
            data["language"] = language

        for attempt in range(1, ATTEMPTS + 1):
            try:
                with path.open("rb") as fh:
                    res = await self._client.post(
                        s.transcribe_url,
                        headers=s.auth_headers(),
                        data=data,
                        files={"file": (path.name, fh, "audio/wav")},
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
            return _text(res)

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
