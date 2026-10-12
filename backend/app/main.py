"""Transcriptie-API en de gebouwde frontend, in één proces.

API (volgt de NL GOV API Design Rules waar dat voor zo'n kleine API zin heeft:
/api/v1, meervoud, problem+json, API-Version-header):

    POST   /api/v1/transcriptions        audio uploaden → 202 + taak
    GET    /api/v1/transcriptions/{id}   status, voortgang en (als klaar) tekst,
                                         met sprekers: ook speakers en segments
    DELETE /api/v1/transcriptions/{id}   annuleren en alles weggooien
    GET    /api/v1/features              wat deze server kan (sprekerherkenning)
    GET    /api/v1/health                voor de health probe
"""

from __future__ import annotations

import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from . import audio
from .config import Settings, load_settings
from .diarizer import Diarizer
from .jobs import JobStore
from .transcriber import Transcriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("transcriptie")

API_VERSION = "1.1.0"

MAX_SPEAKERS = 20

SECURITY_HEADERS = {
    # Alleen de eigen origin. style-src houdt 'unsafe-inline' omdat de
    # NLDD-webcomponenten (Lit) stijlen in de shadow DOM zetten; scripts blijven
    # strikt. blob: is nodig om een eigen opname terug te luisteren.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    # Microfoon alleen voor deze site zelf; de rest heeft de app niet nodig.
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=(), usb=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def problem(status: int, title: str, detail: str = "") -> JSONResponse:
    body = {"status": status, "title": title}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def create_app(settings: Settings | None = None, store: JobStore | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        transcriber = None
        if store is None:
            transcriber = Transcriber(settings)
            diarizer = Diarizer(settings) if settings.diarization == "local" else None
            app.state.store = JobStore(settings, transcriber, diarizer)
        else:
            app.state.store = store
        log.info("transcriptiedienst: %s (model %s)", settings.transcribe_url, settings.transcribe_model)
        log.info("sprekerherkenning: %s", settings.diarization)
        yield
        await app.state.store.shutdown()
        if transcriber:
            await transcriber.aclose()

    app = FastAPI(title="Transcriptie", version=API_VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        if request.url.path.startswith("/api/"):
            response.headers["API-Version"] = API_VERSION
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/v1/features")
    async def features(request: Request) -> dict:
        return {"speakers": request.app.state.store.speakers_available()}

    @app.post("/api/v1/transcriptions", status_code=202)
    async def create(
        request: Request,
        file: UploadFile,
        language: str | None = Form(None),
        speakers: str | None = Form(None),
        num_speakers: str | None = Form(None, alias="numSpeakers"),
    ):
        store: JobStore = request.app.state.store
        want_speakers = (speakers or "").strip().lower() in ("true", "1", "ja")
        if want_speakers and not store.speakers_available():
            return problem(
                422, "Sprekerherkenning niet beschikbaar", "Zet sprekerherkenning uit en probeer het opnieuw."
            )
        count: int | None = None
        if want_speakers and (num_speakers or "").strip():
            try:
                count = int(num_speakers)
            except ValueError:
                count = -1
            if not 1 <= count <= MAX_SPEAKERS:
                return problem(422, "Ongeldig aantal sprekers", f"Kies een aantal van 1 tot {MAX_SPEAKERS}.")

        max_bytes = settings.max_upload_bytes
        max_mb = max_bytes // (1024 * 1024)
        declared = int(request.headers.get("content-length") or 0)
        if declared > max_bytes + 1024 * 1024:
            return problem(413, "Bestand te groot", f"Het maximum is {max_mb} MB.")

        workdir = store.new_workdir()
        suffix = Path(file.filename or "").suffix[:10] or ".bin"
        upload = workdir / f"upload{suffix}"
        try:
            written = 0
            with upload.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise _TooLarge
                    out.write(chunk)
            if written == 0:
                raise audio.AudioError("Het bestand is leeg.")

            # Snelle check vooraf, zodat een te lange opname meteen een fout
            # geeft in plaats van na het omzetten. Opnames uit de browser
            # (webm) hebben vaak geen duur in de header; die meet de taak na het
            # omzetten opnieuw.
            duration = await audio.probe_duration(upload)
            if duration > settings.max_duration_seconds + 1:
                hours = settings.max_duration_seconds / 3600
                return _cleanup(
                    workdir,
                    problem(
                        422,
                        "Opname te lang",
                        f"De opname duurt {duration / 60:.0f} minuten. Het maximum is {hours:g} uur.",
                    ),
                )
        except _TooLarge:
            return _cleanup(workdir, problem(413, "Bestand te groot", f"Het maximum is {max_mb} MB."))
        except audio.AudioError as exc:
            return _cleanup(workdir, problem(415, "Geen bruikbare audio", str(exc)))
        except BaseException:
            shutil.rmtree(workdir, ignore_errors=True)
            raise

        lang = (language if language is not None else settings.language).strip() or None
        job = store.start(upload, file.filename or "audio", lang, workdir, want_speakers, count)
        return JSONResponse(
            job.public(), status_code=202, headers={"Location": f"/api/v1/transcriptions/{job.id}"}
        )

    @app.get("/api/v1/transcriptions/{job_id}")
    async def status(request: Request, job_id: str):
        job = request.app.state.store.get(job_id)
        if not job:
            return problem(404, "Niet gevonden", "Deze transcriptie bestaat niet (meer).")
        return job.public()

    @app.delete("/api/v1/transcriptions/{job_id}", status_code=204)
    async def delete(request: Request, job_id: str):
        if not await request.app.state.store.delete(job_id):
            return problem(404, "Niet gevonden", "Deze transcriptie bestaat niet (meer).")
        return Response(status_code=204)

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def api_not_found(rest: str):
        return problem(404, "Niet gevonden")

    _mount_frontend(app, settings.static_dir)
    return app


class _TooLarge(Exception):
    pass


def _cleanup(workdir: Path, response: Response) -> Response:
    shutil.rmtree(workdir, ignore_errors=True)
    return response


def _mount_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serveer dist/ met een SPA-fallback. Lokaal (npm run dev) doet Vite dit."""
    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        index = root / "index.html"
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            # Alles onder assets/ heeft een hash in de naam: voor altijd cachen.
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return problem(404, "Niet gevonden", "De frontend is niet gebouwd (npm run build).")


app = create_app()
