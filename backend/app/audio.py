"""Audio meten, omzetten en opknippen met ffmpeg/ffprobe.

Waarom knippen: Voxtral verwerkt ongeveer 30 minuten audio per aanvraag, en
één aanvraag van een uur zou elke time-out onderweg raken. We knippen daarom in
stukken van rond de 10 minuten, en dan bij voorkeur in een stilte, zodat er
geen woord doormidden gaat.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

# 16 kHz mono is wat Voxtral intern gebruikt: kleiner bestand,
# zelfde resultaat.
SAMPLE_RATE = 16_000

_SILENCE_START = re.compile(r"silence_start: (-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end: (-?[\d.]+)")


class AudioError(Exception):
    """Het bestand is geen bruikbare audio."""


async def _run(*args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await proc.communicate()
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


async def probe_duration(path: Path) -> float:
    """Duur in seconden; AudioError als er geen audiostroom in zit."""
    code, out, _ = await _run(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type:format=duration",
        "-of",
        "json",
        str(path),
    )
    if code != 0:
        raise AudioError("Dit bestand kan niet als audio worden gelezen.")
    info = json.loads(out or "{}")
    if not info.get("streams"):
        raise AudioError("Dit bestand bevat geen geluid.")
    try:
        duration = float(info["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        duration = 0.0
    return duration


async def to_wav(src: Path, dest: Path) -> float:
    """Zet om naar 16 kHz mono wav en geeft de werkelijke duur terug.

    Browseropnames (webm van MediaRecorder) hebben vaak geen duur in de
    header; na het omzetten wel. Daarom meten we hier opnieuw.
    """
    code, _, _ = await _run(
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        str(dest),
    )
    if code != 0:
        raise AudioError("Het geluid in dit bestand kan niet worden omgezet.")
    return (dest.stat().st_size - 44) / (SAMPLE_RATE * 2)


async def detect_silences(
    path: Path, noise_db: int = -35, min_seconds: float = 0.4
) -> list[tuple[float, float]]:
    _, _, err = await _run(
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-i",
        str(path),
        "-af",
        f"silencedetect=n={noise_db}dB:d={min_seconds}",
        "-f",
        "null",
        "-",
    )
    return parse_silences(err)


def parse_silences(ffmpeg_log: str) -> list[tuple[float, float]]:
    silences: list[tuple[float, float]] = []
    start: float | None = None
    for line in ffmpeg_log.splitlines():
        if m := _SILENCE_START.search(line):
            start = max(0.0, float(m.group(1)))
        elif (m := _SILENCE_END.search(line)) and start is not None:
            silences.append((start, float(m.group(1))))
            start = None
    return silences


def plan_segments(
    duration: float, silences: list[tuple[float, float]], chunk: float, window: float
) -> list[tuple[float, float]]:
    """Verdeel [0, duration] in stukken van hoogstens `chunk` seconden.

    Elke knip valt in het midden van de stilte die het dichtst bij de
    doelgrens ligt, maar nooit meer dan `window` seconden ervoor (en nooit
    erna, zodat geen stuk langer wordt dan `chunk`). Zonder stilte in dat
    venster knippen we op de grens zelf.
    """
    if duration <= 0:
        return []
    mids = sorted((s + e) / 2 for s, e in silences)
    segments: list[tuple[float, float]] = []
    pos = 0.0
    while duration - pos > chunk:
        target = pos + chunk
        candidates = [m for m in mids if target - window <= m <= target and m > pos + 1]
        cut = min(candidates, key=lambda m: target - m) if candidates else target
        segments.append((pos, cut))
        pos = cut
    segments.append((pos, duration))
    return segments


async def extract(src: Path, start: float, end: float, dest: Path) -> None:
    code, _, _ = await _run(
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(src),
        "-c",
        "copy",
        str(dest),
    )
    if code != 0:
        raise AudioError("Het opknippen van de audio is mislukt.")
