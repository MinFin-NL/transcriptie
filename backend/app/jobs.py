"""Transcriptietaken: in het geheugen, met opruimen.

Een taak leeft alleen in dit proces. Daarom draait de Container App met
precies één replica (zie azure-pipelines.yml). Audio staat alleen tijdens de
verwerking op schijf, in een tijdelijke map die daarna wordt gewist; het
transcript verdwijnt na RESULT_TTL_SECONDS uit het geheugen.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from . import audio
from .config import Settings
from .transcriber import TranscriberError

log = logging.getLogger(__name__)


class Status(StrEnum):
    QUEUED = "queued"
    CONVERTING = "converting"
    TRANSCRIBING = "transcribing"
    DONE = "done"
    FAILED = "failed"


class TooLong(Exception):
    def __init__(self, duration: float):
        super().__init__(duration)
        self.duration = duration


class TranscribeFn(Protocol):
    async def transcribe(self, path: Path, language: str | None) -> str: ...


@dataclass
class Job:
    id: str
    filename: str
    language: str | None
    workdir: Path
    status: Status = Status.QUEUED
    duration_seconds: float | None = None
    chunks_total: int = 0
    chunks_done: int = 0
    text: str = ""
    error: str = ""
    created: float = field(default_factory=time.monotonic)
    finished: float | None = None
    task: asyncio.Task | None = None

    def public(self) -> dict:
        body: dict = {
            "id": self.id,
            "status": self.status.value,
            "filename": self.filename,
            "durationSeconds": round(self.duration_seconds, 1) if self.duration_seconds else None,
            "progress": {"completed": self.chunks_done, "total": self.chunks_total},
        }
        if self.status is Status.DONE:
            body["text"] = self.text
        if self.status is Status.FAILED:
            body["error"] = self.error
        return body


class JobStore:
    def __init__(self, settings: Settings, transcriber: TranscribeFn):
        self.settings = settings
        self.transcriber = transcriber
        self.jobs: dict[str, Job] = {}
        self._slots = asyncio.Semaphore(settings.concurrency)

    def new_workdir(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="transcriptie-"))

    def get(self, job_id: str) -> Job | None:
        self.purge()
        return self.jobs.get(job_id)

    def start(self, upload: Path, filename: str, language: str | None, workdir: Path) -> Job:
        self.purge()
        job = Job(id=str(uuid.uuid4()), filename=filename, language=language, workdir=workdir)
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self._run(job, upload))
        return job

    async def delete(self, job_id: str) -> bool:
        job = self.jobs.pop(job_id, None)
        if not job:
            return False
        if job.task and not job.task.done():
            job.task.cancel()
            # _run vangt zijn eigen fouten af; hier komt alleen de annulering terug.
            with contextlib.suppress(asyncio.CancelledError):
                await job.task
        shutil.rmtree(job.workdir, ignore_errors=True)
        return True

    def purge(self) -> None:
        now = time.monotonic()
        ttl = self.settings.result_ttl_seconds
        for job_id, job in list(self.jobs.items()):
            if job.finished is not None and now - job.finished > ttl:
                self.jobs.pop(job_id, None)
                shutil.rmtree(job.workdir, ignore_errors=True)

    async def shutdown(self) -> None:
        for job_id in list(self.jobs):
            await self.delete(job_id)

    async def _run(self, job: Job, upload: Path) -> None:
        s = self.settings
        try:
            async with self._slots:
                job.status = Status.CONVERTING
                wav = job.workdir / "audio.wav"
                job.duration_seconds = await audio.to_wav(upload, wav)
                upload.unlink(missing_ok=True)
                if job.duration_seconds > s.max_duration_seconds:
                    raise TooLong(job.duration_seconds)

                silences = await audio.detect_silences(wav)
                segments = audio.plan_segments(
                    job.duration_seconds, silences, s.chunk_seconds, s.split_window_seconds
                )
                job.chunks_total = len(segments)
                job.status = Status.TRANSCRIBING
                log.info("taak %s: %.0f s audio, %d stukken", job.id, job.duration_seconds, len(segments))

                parts: list[str] = []
                for i, (start, end) in enumerate(segments):
                    piece = job.workdir / f"deel-{i:03d}.wav"
                    await audio.extract(wav, start, end, piece)
                    text = await self.transcriber.transcribe(piece, job.language)
                    piece.unlink(missing_ok=True)
                    if text:
                        parts.append(text)
                    job.chunks_done = i + 1

                if not parts:
                    raise TranscriberError("Er is geen spraak herkend in deze opname.")
                job.text = "\n\n".join(parts)
                job.status = Status.DONE
        except asyncio.CancelledError:
            raise
        except TooLong as exc:
            job.status = Status.FAILED
            job.error = (
                f"De opname duurt {_minutes(exc.duration)}. "
                f"Het maximum is {_minutes(s.max_duration_seconds)}."
            )
        except (audio.AudioError, TranscriberError) as exc:
            job.status = Status.FAILED
            job.error = str(exc)
        except Exception:
            log.exception("taak %s mislukt", job.id)
            job.status = Status.FAILED
            job.error = "Er ging iets onverwachts mis bij het transcriberen."
        finally:
            job.finished = time.monotonic()
            # Audio nooit langer bewaren dan nodig: weg zodra de taak klaar is.
            shutil.rmtree(job.workdir, ignore_errors=True)


def _minutes(seconds: float) -> str:
    total = round(seconds / 60)
    hours, minutes = divmod(total, 60)
    if hours and minutes:
        return f"{hours} uur en {minutes} minuten"
    if hours:
        return f"{hours} uur"
    return f"{minutes} minuten"
