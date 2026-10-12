// Praat met de eigen backend (/api/v1/transcriptions). Die knipt de audio op,
// stuurt de stukken naar de transcriptiedienst en houdt de voortgang bij. De
// browser ziet de transcriptiedienst en zijn sleutel nooit.
//
// Een transcriptie is een taak: uploaden (met voortgang), dan pollen tot hij
// klaar is. Eén aanvraag die wacht op twee uur audio zou elke time-out
// onderweg raken, en zou de gebruiker niets laten zien.

export const API = '/api/v1/transcriptions'
export const FEATURES = '/api/v1/features'

export const LANGUAGE = import.meta.env.VITE_TRANSCRIBE_LANGUAGE ?? 'nl'

// Moeten gelijk zijn aan MAX_AUDIO_SECONDS en MAX_UPLOAD_MB van de backend; de
// backend controleert ook, dit is voor snelle feedback vóór het uploaden.
export const MAX_DURATION_SECONDS = Number(import.meta.env.VITE_MAX_AUDIO_MINUTES || 120) * 60
export const MAX_UPLOAD_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB) || 500
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

const POLL_MS = 2000

/** Een fout met een tekst die zo voor de gebruiker te lezen is. */
export class TranscriptionError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'TranscriptionError'
    this.status = status
  }
}

export type JobStatus = 'queued' | 'converting' | 'diarizing' | 'transcribing' | 'done' | 'failed'

/** Een beurt: wie sprak, van wanneer tot wanneer (seconden), en wat. */
export interface Segment {
  speaker: string
  start: number
  end: number
  text: string
}

/** Het resultaat. `segments` alleen als er om sprekers is gevraagd. */
export interface Transcript {
  text: string
  segments?: Segment[]
  durationSeconds?: number | null
}

export interface SpeakerOptions {
  enabled: boolean
  /** Aantal sprekers als de gebruiker het weet; maakt de indeling betrouwbaarder. */
  count?: number
}

export interface Job {
  id: string
  status: JobStatus
  filename: string
  durationSeconds: number | null
  progress: { completed: number; total: number }
  text?: string
  segments?: Segment[]
  error?: string
}

export type Progress =
  | { phase: 'uploading'; fraction: number }
  | { phase: 'queued' | 'converting' | 'diarizing' }
  | { phase: 'transcribing'; completed: number; total: number; durationSeconds: number | null }

export interface TranscribeOptions {
  signal?: AbortSignal
  language?: string
  speakers?: SpeakerOptions
  onProgress?: (p: Progress) => void
}

export function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

export async function transcribe(
  audio: Blob,
  filename: string,
  { signal, language = LANGUAGE, speakers, onProgress }: TranscribeOptions = {},
): Promise<Transcript> {
  const job = await upload(audio, filename, language, speakers, signal, (fraction) =>
    onProgress?.({ phase: 'uploading', fraction }),
  )
  try {
    return await poll(job, signal, onProgress)
  } catch (err) {
    // Geannuleerd: de backend stopt en gooit de audio meteen weg.
    if (isAbort(err)) void fetch(`${API}/${job.id}`, { method: 'DELETE' }).catch(() => {})
    throw err
  }
}

// XMLHttpRequest in plaats van fetch: alleen die meldt uploadvoortgang, en bij
// een bestand van 100 MB wil je zien dat er iets gebeurt.
function upload(
  audio: Blob,
  filename: string,
  language: string,
  speakers: SpeakerOptions | undefined,
  signal: AbortSignal | undefined,
  onUpload: (fraction: number) => void,
): Promise<Job> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('Geannuleerd', 'AbortError'))

    const body = new FormData()
    body.append('file', audio, filename)
    body.append('language', language)
    if (speakers?.enabled) {
      body.append('speakers', 'true')
      if (speakers.count) body.append('numSpeakers', String(speakers.count))
    }

    const xhr = new XMLHttpRequest()
    xhr.open('POST', API)
    xhr.responseType = 'text'
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onUpload(e.loaded / e.total)
    }
    xhr.onload = () => {
      const data = parse(xhr.responseText)
      if (xhr.status === 202 && data && typeof data.id === 'string') resolve(data as unknown as Job)
      else reject(new TranscriptionError(messageFor(xhr.status, data), xhr.status))
    }
    xhr.onerror = () =>
      reject(new TranscriptionError('De server is niet bereikbaar. Controleer je verbinding en probeer het opnieuw.'))
    xhr.onabort = () => reject(new DOMException('Geannuleerd', 'AbortError'))
    signal?.addEventListener('abort', () => xhr.abort(), { once: true })
    onUpload(0)
    xhr.send(body)
  })
}

async function poll(job: Job, signal: AbortSignal | undefined, onProgress?: TranscribeOptions['onProgress']) {
  let current = job
  for (;;) {
    report(current, onProgress)
    if (current.status === 'done') {
      const text = current.text?.trim() ?? ''
      if (!text) throw new TranscriptionError('Er is geen spraak herkend in deze opname.')
      return { text, segments: current.segments, durationSeconds: current.durationSeconds }
    }
    if (current.status === 'failed') {
      throw new TranscriptionError(current.error || 'Het transcriberen is mislukt.')
    }
    await wait(POLL_MS, signal)
    current = await fetchJob(current.id, signal)
  }
}

async function fetchJob(id: string, signal?: AbortSignal): Promise<Job> {
  let res: Response
  try {
    res = await fetch(`${API}/${id}`, { signal })
  } catch (err) {
    if (isAbort(err)) throw err
    throw new TranscriptionError('De verbinding met de server is weggevallen.')
  }
  const data = parse(await res.text())
  if (!res.ok || !data) {
    throw new TranscriptionError(
      res.status === 404
        ? 'Deze transcriptie bestaat niet meer. Misschien is de server herstart; probeer het opnieuw.'
        : messageFor(res.status, data),
      res.status,
    )
  }
  return data as unknown as Job
}

function report(job: Job, onProgress?: TranscribeOptions['onProgress']) {
  if (!onProgress) return
  if (job.status === 'queued' || job.status === 'converting' || job.status === 'diarizing')
    onProgress({ phase: job.status })
  else if (job.status === 'transcribing')
    onProgress({
      phase: 'transcribing',
      completed: job.progress.completed,
      total: job.progress.total,
      durationSeconds: job.durationSeconds,
    })
}

/** Wat deze server kan. Gaat het mis, dan doen we alsof er geen sprekers zijn. */
export async function fetchFeatures(): Promise<{ speakers: boolean }> {
  try {
    const res = await fetch(FEATURES)
    const data = res.ok ? parse(await res.text()) : null
    return { speakers: data?.speakers === true }
  } catch {
    return { speakers: false }
  }
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms)
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(t)
        reject(new DOMException('Geannuleerd', 'AbortError'))
      },
      { once: true },
    )
  })
}

function parse(raw: string): Record<string, unknown> | null {
  try {
    const data = JSON.parse(raw)
    return data && typeof data === 'object' ? data : null
  } catch {
    return null
  }
}

// De backend geeft problem+json ({ title, detail }) met Nederlandse teksten.
function messageFor(status: number, data: Record<string, unknown> | null): string {
  const detail = typeof data?.detail === 'string' ? data.detail : ''
  const title = typeof data?.title === 'string' ? data.title : ''
  if (detail) return title ? `${title}: ${detail}` : detail
  if (status === 413) return `Het bestand is te groot. Het maximum is ${MAX_UPLOAD_MB} MB.`
  if (status === 502 || status === 503 || status === 504)
    return 'De server is even niet beschikbaar. Probeer het over een minuut opnieuw.'
  return `Er ging iets mis (fout ${status || 'onbekend'}). Probeer het opnieuw.`
}
