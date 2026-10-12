import { computed, onScopeDispose, ref, shallowRef } from 'vue'
import {
  isAbort,
  transcribe,
  TranscriptionError,
  type Progress,
  type Segment,
  type SpeakerOptions,
} from '../services/transcriptionService'
import { mergeSpeakers, reassignTurn, speakerLabel, type Names } from '../utils/turns'

export type TranscriptionStatus = 'idle' | 'busy' | 'done' | 'error'

/**
 * De toestand van één transcriptie: idle → busy → done | error, met annuleren
 * en een teller voor hoe lang het al duurt. Het transcript leeft alleen in het
 * geheugen; er gaat niets naar localStorage.
 *
 * Met sprekers zijn er ook beurten (`segments`) en de namen die de gebruiker
 * geeft. Die namen blijven in de browser: ze gaan nooit naar de server.
 */
export function useTranscription(run: typeof transcribe = transcribe) {
  const status = ref<TranscriptionStatus>('idle')
  const text = ref('')
  const segments = ref<Segment[] | null>(null)
  const names = ref<Names>({})
  const durationSeconds = ref<number | null>(null)
  const error = ref('')
  const filename = ref('')
  const elapsedSeconds = ref(0)
  const progress = shallowRef<Progress>({ phase: 'uploading', fraction: 0 })

  let source: { audio: Blob; filename: string; speakers?: SpeakerOptions } | null = null
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setInterval> | undefined

  function stopTimer() {
    clearInterval(timer)
    timer = undefined
  }

  async function start(audio: Blob, name: string, speakers?: SpeakerOptions) {
    cancel()
    source = { audio, filename: name, speakers }
    filename.value = name
    clearResult()
    error.value = ''
    elapsedSeconds.value = 0
    progress.value = { phase: 'uploading', fraction: 0 }
    status.value = 'busy'

    const started = Date.now()
    timer = setInterval(() => {
      elapsedSeconds.value = Math.floor((Date.now() - started) / 1000)
    }, 1000)

    const ctrl = new AbortController()
    controller = ctrl
    try {
      const result = await run(audio, name, {
        signal: ctrl.signal,
        speakers,
        onProgress: (p) => {
          if (controller === ctrl) progress.value = p
        },
      })
      if (controller !== ctrl) return
      text.value = result.text
      segments.value = result.segments?.length ? result.segments : null
      durationSeconds.value = result.durationSeconds ?? null
      status.value = 'done'
    } catch (err) {
      if (controller !== ctrl || isAbort(err)) return
      error.value =
        err instanceof TranscriptionError ? err.message : 'Er ging iets onverwachts mis. Probeer het opnieuw.'
      status.value = 'error'
    } finally {
      if (controller === ctrl) {
        controller = null
        stopTimer()
      }
    }
  }

  /** Breekt een lopende aanvraag af en gaat terug naar het begin. */
  function cancel() {
    controller?.abort()
    controller = null
    stopTimer()
    if (status.value === 'busy') status.value = 'idle'
  }

  function retry() {
    if (source) void start(source.audio, source.filename, source.speakers)
  }

  function clearResult() {
    text.value = ''
    segments.value = null
    names.value = {}
    durationSeconds.value = null
  }

  /** Geeft een spreker een naam; leeg maakt er weer "Spreker N" van. */
  function rename(speaker: string, name: string) {
    names.value = { ...names.value, [speaker]: name }
  }

  /** Eén persoon die als twee sprekers is herkend. */
  function mergeSpeaker(from: string, into: string) {
    if (!segments.value || from === into) return
    segments.value = mergeSpeakers(segments.value, from, into)
    const { [from]: _gone, ...rest } = names.value
    names.value = rest
  }

  function reassign(index: number, speaker: string) {
    if (segments.value) segments.value = reassignTurn(segments.value, index, speaker)
  }

  function editTurn(index: number, value: string) {
    if (!segments.value?.[index]) return
    segments.value = segments.value.map((s, i) => (i === index ? { ...s, text: value } : s))
  }

  function label(speaker: string) {
    return speakerLabel(speaker, names.value)
  }

  function reset() {
    cancel()
    source = null
    status.value = 'idle'
    clearResult()
    error.value = ''
    filename.value = ''
    elapsedSeconds.value = 0
  }

  onScopeDispose(cancel)

  return {
    status,
    text,
    segments,
    names,
    durationSeconds,
    error,
    filename,
    elapsedSeconds,
    progress,
    busy: computed(() => status.value === 'busy'),
    start,
    cancel,
    retry,
    reset,
    rename,
    mergeSpeaker,
    reassign,
    editTurn,
    label,
  }
}
