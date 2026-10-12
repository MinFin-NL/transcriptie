"""Sprekerherkenning (diarisatie) in dit proces, met pyannote.

Voor als de transcriptiedienst zelf geen sprekers levert, zoals Voxtral in
Ollama. Het model is pyannote speaker-diarization-community-1 (CC-BY-4.0),
hetzelfde dat vlam-api gebruikt. Er gaat geen audio naar een andere partij: het
model draait hier. Alleen lokaal: in productie herkent vlam-api de sprekers,
en het image heeft pyannote niet. Hugging Face haalt het model de eerste keer
op; omdat het model achter een gebruikersovereenkomst staat, moet je
daarvoor één keer ingelogd zijn (`hf auth login` of HF_TOKEN). Daarna staat het
in de cache en is er geen sleutel meer nodig. DIARIZATION_MODEL mag ook een map
zijn waarin je het model zelf hebt gezet.

Stemkenmerken (embeddings) bestaan alleen in het geheugen, tijdens één
diarisatie, en worden niet bewaard.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import wave
from pathlib import Path

from .audio import SAMPLE_RATE
from .config import Settings
from .turns import Segment

log = logging.getLogger(__name__)


class DiarizerError(Exception):
    """Een fout met een tekst die zo voor de gebruiker te lezen is."""


class Diarizer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._pipeline = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        """Kan dit proces sprekers herkennen? Zonder het model te laden: dat
        kost seconden en lokaal misschien een download."""
        try:
            import pyannote.audio  # noqa: F401
            from huggingface_hub import get_token, try_to_load_from_cache
        except ImportError:
            return False
        # Een map met het model (zelf gedownload): geen sleutel nodig.
        if Path(self.settings.diarization_model).is_dir():
            return True
        # Een sleutel uit de omgeving of van `hf auth login`: dan kan het model
        # worden opgehaald.
        if self.settings.hf_token or get_token():
            return True
        return isinstance(try_to_load_from_cache(self.settings.diarization_model, "config.yaml"), str)

    async def diarize(self, wav: Path, num_speakers: int | None) -> list[Segment]:
        # pyannote rekent minuten op de CPU; niet op de event loop, anders
        # beantwoordt de API intussen geen statusvragen meer.
        return await asyncio.to_thread(self._diarize, wav, num_speakers)

    def _load(self):
        with self._lock:
            if self._pipeline is not None:
                return self._pipeline
            try:
                import torch
                from pyannote.audio import Pipeline
            except ImportError as exc:
                raise DiarizerError("Sprekerherkenning is op deze server niet geïnstalleerd.") from exc
            try:
                pipeline = Pipeline.from_pretrained(
                    self.settings.diarization_model, token=self.settings.hf_token or None
                )
            except Exception as exc:
                log.exception("sprekermodel laden mislukt")
                raise DiarizerError("Het model voor sprekerherkenning kon niet worden geladen.") from exc
            if pipeline is None:
                raise DiarizerError("Het model voor sprekerherkenning kon niet worden geladen.")
            if torch.cuda.is_available():
                pipeline.to(torch.device("cuda"))
            self._pipeline = pipeline
            return pipeline

    def _diarize(self, wav: Path, num_speakers: int | None) -> list[Segment]:
        pipeline = self._load()
        kwargs = {"num_speakers": num_speakers} if num_speakers else {}
        try:
            output = pipeline({"waveform": _read_wav(wav), "sample_rate": SAMPLE_RATE}, **kwargs)
        except Exception as exc:
            log.exception("diarisatie mislukt")
            raise DiarizerError("Het herkennen van de sprekers is mislukt.") from exc
        # pyannote 4 geeft ook een versie zonder overlap: precies één spreker
        # tegelijk, wat we nodig hebben om per beurt te knippen.
        annotation = getattr(output, "exclusive_speaker_diarization", None) or getattr(
            output, "speaker_diarization", output
        )
        return [
            Segment(turn.start, turn.end, str(speaker))
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ]


def _read_wav(path: Path):
    """16 kHz mono pcm_s16le (van audio.to_wav) als tensor (1, n), in het
    geheugen; dan heeft pyannote geen eigen audiodecoder nodig."""
    import numpy as np
    import torch

    with wave.open(str(path), "rb") as w:
        frames = w.readframes(w.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return torch.from_numpy(samples).unsqueeze(0)
