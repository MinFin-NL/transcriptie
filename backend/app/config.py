"""Instellingen uit de omgeving. Lokaal staan ze in .env.local (zie
.env.example); in Azure zet de pipeline ze op de Container App."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Lokaal: Voxtral Small 24B in Ollama, via Ollama's transcriptie-endpoint.
# In productie: vlam-api van vlam.ai (SSC-ICT); URL, sleutel en (eventueel)
# model komen uit de secrets. Zie docs/vlam-ai.md.
DEFAULT_URL = "http://localhost:11434/v1/audio/transcriptions"
DEFAULT_MODEL = "hf.co/bartowski/mistralai_Voxtral-Small-24B-2507-GGUF:Q4_K_M"

# Sprekerherkenning: hetzelfde model dat vlam-api gebruikt (CC-BY-4.0).
DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"
DIARIZATION_MODES = ("local", "service", "off")


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _load_dotenv(path: Path) -> None:
    """Minimale .env-lezer voor lokaal draaien; echte omgevingsvariabelen winnen."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    transcribe_url: str = field(default_factory=lambda: os.environ.get("TRANSCRIBE_URL", "") or DEFAULT_URL)
    transcribe_model: str = field(
        default_factory=lambda: os.environ.get("TRANSCRIBE_MODEL", "") or DEFAULT_MODEL
    )
    api_key: str = field(default_factory=lambda: os.environ.get("TRANSCRIBE_API_KEY", ""))
    # "Authorization" (standaard) krijgt "Bearer " voor de sleutel; elke andere
    # header (bijv. "api-key") krijgt de sleutel zoals hij is.
    api_key_header: str = field(
        default_factory=lambda: os.environ.get("TRANSCRIBE_API_KEY_HEADER", "") or "Authorization"
    )
    language: str = field(default_factory=lambda: os.environ.get("TRANSCRIBE_LANGUAGE", "nl"))

    # Grenzen. 2 uur audio; de bestandsgrootte ruim genoeg voor 2 uur mp3/m4a.
    max_duration_seconds: int = field(default_factory=lambda: _int("MAX_AUDIO_SECONDS", 2 * 60 * 60))
    max_upload_bytes: int = field(default_factory=lambda: _int("MAX_UPLOAD_MB", 500) * 1024 * 1024)

    # Voxtral kan ~30 minuten per aanvraag; 10 minuten houdt elke aanvraag kort
    # (ruim binnen time-outs) en geeft de gebruiker regelmatig voortgang.
    chunk_seconds: int = field(default_factory=lambda: _int("CHUNK_SECONDS", 600))
    # Hoe ver een knip vóór de doelgrens mag vallen om in een stilte te landen.
    split_window_seconds: int = field(default_factory=lambda: _int("SPLIT_WINDOW_SECONDS", 90))
    chunk_timeout_seconds: int = field(default_factory=lambda: _int("CHUNK_TIMEOUT_SECONDS", 900))
    # Hoeveel transcripties tegelijk; lokaal kan Ollama er maar één tegelijk aan.
    concurrency: int = field(default_factory=lambda: _int("TRANSCRIBE_CONCURRENCY", 1))
    # Een klaar transcript blijft zo lang in het geheugen, daarna is het weg.
    result_ttl_seconds: int = field(default_factory=lambda: _int("RESULT_TTL_SECONDS", 60 * 60))

    # Sprekerherkenning. "local": pyannote in dit proces, daarna per beurt naar
    # de transcriptiedienst (Ollama/Voxtral levert zelf geen sprekers).
    # "service": de transcriptiedienst doet het zelf (vlam-api, diarized_json).
    # "off": geen sprekers.
    diarization: str = field(
        default_factory=lambda: (os.environ.get("DIARIZATION", "") or "local").strip().lower()
    )
    diarization_model: str = field(
        default_factory=lambda: os.environ.get("DIARIZATION_MODEL", "") or DEFAULT_DIARIZATION_MODEL
    )
    # Alleen nodig om het model de eerste keer op te halen; in het image staat
    # het er al in.
    hf_token: str = field(default_factory=lambda: os.environ.get("HF_TOKEN", ""))
    # vlam-api diariseert per aanvraag: "spreker 1" in stuk 2 is niet per se
    # "spreker 1" in stuk 1. Daarom bij sprekerherkenning de hele opname in één
    # keer; alleen als de dienst een grens heeft, knippen we toch.
    diarize_chunk_seconds: int = field(default_factory=lambda: _int("DIARIZE_CHUNK_SECONDS", 2 * 60 * 60))
    # Een hele opname van 2 uur in één aanvraag duurt langer dan een stuk van 10
    # minuten.
    diarize_timeout_seconds: int = field(default_factory=lambda: _int("DIARIZE_TIMEOUT_SECONDS", 60 * 60))

    static_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("STATIC_DIR", "") or Path(__file__).resolve().parents[2] / "dist"
        )
    )

    def __post_init__(self) -> None:
        if self.diarization not in DIARIZATION_MODES:
            raise ValueError(f"DIARIZATION moet een van {', '.join(DIARIZATION_MODES)} zijn")

    def auth_headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        if self.api_key_header.lower() == "authorization" and not self.api_key.lower().startswith("bearer "):
            return {"Authorization": f"Bearer {self.api_key}"}
        return {self.api_key_header: self.api_key}


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[2]
    _load_dotenv(root / ".env.local")
    return Settings()
