# Eén image: de backend (FastAPI) serveert ook de gebouwde
# frontend. Lokaal draai je ze los (npm run dev + uvicorn), zie README.

# ── Stap 1: de Vue-app bouwen ────────────────────────────────────────────────
FROM node:26-alpine AS frontend

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Komen in de bundel terecht; dus nooit iets geheims.
ARG VITE_TRANSCRIBE_LANGUAGE=nl
ARG VITE_MAX_AUDIO_MINUTES=120
ARG VITE_MAX_UPLOAD_MB=500
ENV VITE_TRANSCRIBE_LANGUAGE=$VITE_TRANSCRIBE_LANGUAGE \
    VITE_MAX_AUDIO_MINUTES=$VITE_MAX_AUDIO_MINUTES \
    VITE_MAX_UPLOAD_MB=$VITE_MAX_UPLOAD_MB

COPY index.html vite.config.ts tsconfig.json tsconfig.node.json ./
COPY src ./src
RUN npm test && npm run build

# ── Stap 2: backend met ffmpeg ───────────────────────────────────────────────
FROM python:3.13-slim

# ffmpeg/ffprobe om audio te meten, om te zetten en op te knippen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
# Zonder de groep `diarization` (pyannote, torch): in productie herkent
# vlam-api de sprekers zelf (DIARIZATION=service).
RUN uv sync --frozen --no-default-groups --no-install-project

COPY backend ./backend
COPY --from=frontend /app/dist ./dist

# Niet als root draaien.
RUN useradd --system --uid 10001 --home /app app && chown -R app /app
USER app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    STATIC_DIR=/app/dist \
    DIARIZATION=service \
    MAX_AUDIO_SECONDS=7200 \
    MAX_UPLOAD_MB=500

EXPOSE 8000

# Eén worker: de taken leven in het geheugen van dit ene proces.
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
