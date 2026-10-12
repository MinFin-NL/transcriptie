"""Beurten: wie sprak wanneer, en wat werd er gezegd.

Pure functies zonder pyannote of torch, zodat ze snel te testen zijn. De
diarisatie (lokaal) en de transcriptiedienst (vlam-api) leveren allebei
segmenten met een sprekerlabel; hier maken we daar leesbare beurten van.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import audio

# Een tussenwerpsel ("ja", "hm") van een ander dat korter is dan dit, laten we
# in de lopende beurt staan. Anders wordt één betoog drie beurten.
MIN_INTERJECTION_SECONDS = 0.7


@dataclass
class Segment:
    start: float
    end: float
    speaker: str
    text: str = ""

    def public(self) -> dict:
        return {
            "speaker": self.speaker,
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "text": self.text,
        }


def merge_turns(segments: list[Segment], min_interjection: float = MIN_INTERJECTION_SECONDS) -> list[Segment]:
    """Voeg opeenvolgende segmenten van dezelfde spreker samen tot beurten.

    Een kort segment van een ander midden in een beurt hoort bij die beurt.
    """
    turns: list[Segment] = []
    for seg in sorted(segments, key=lambda s: s.start):
        if seg.end <= seg.start:
            continue
        if turns and (seg.speaker == turns[-1].speaker or seg.end - seg.start < min_interjection):
            turns[-1].end = max(turns[-1].end, seg.end)
            continue
        turns.append(Segment(seg.start, seg.end, seg.speaker))
    return turns


def split_long(
    turns: list[Segment], silences: list[tuple[float, float]], chunk: float, window: float
) -> list[Segment]:
    """Knip beurten langer dan `chunk` op, bij voorkeur in een stilte.

    Zelfde regels als het knippen van een hele opname (audio.plan_segments),
    maar dan binnen één beurt.
    """
    out: list[Segment] = []
    for turn in turns:
        length = turn.end - turn.start
        if length <= chunk:
            out.append(turn)
            continue
        inside = [(s - turn.start, e - turn.start) for s, e in silences if s > turn.start and e < turn.end]
        for start, end in audio.plan_segments(length, inside, chunk, window):
            out.append(Segment(turn.start + start, turn.start + end, turn.speaker))
    return out


def normalize(segments: list[Segment]) -> list[Segment]:
    """Maak het eindresultaat: sprekers S1, S2, … in volgorde van eerste keer
    spreken, geen lege beurten, en opeenvolgende beurten van dezelfde spreker
    samengevoegd.

    De labels van de dienst (SPEAKER_00) of van pyannote zeggen niets; de
    gebruiker geeft in de browser namen.
    """
    ids: dict[str, str] = {}
    out: list[Segment] = []
    for seg in sorted(segments, key=lambda s: s.start):
        text = seg.text.strip()
        if not text:
            continue
        speaker = ids.setdefault(seg.speaker, f"S{len(ids) + 1}")
        if out and out[-1].speaker == speaker:
            out[-1].end = max(out[-1].end, seg.end)
            out[-1].text = f"{out[-1].text} {text}"
            continue
        out.append(Segment(seg.start, seg.end, speaker, text))
    return out


def speakers_of(segments: list[Segment]) -> list[str]:
    seen: list[str] = []
    for seg in segments:
        if seg.speaker not in seen:
            seen.append(seg.speaker)
    return seen
