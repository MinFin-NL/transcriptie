import { computed, onScopeDispose, ref, shallowRef } from 'vue'
import { isAbort, transcribe, TranscriptionError, type Progress } from '../services/transcriptionService'

export type TranscriptionStatus = 'idle' | 'busy' | 'done' | 'error'

/**
 * De toestand van één transcriptie: idle → busy → done | error, met annuleren
 * en een teller voor hoe lang het al duurt. Het transcript leeft alleen in het
 * geheugen; er gaat niets naar localStorage.
 */
export function useTranscription(run: typeof transcribe = transcribe) {
  const status = ref<TranscriptionStatus>('idle')
  const text = ref('')
  const error = ref('')
  const filename = ref('')
  const elapsedSeconds = ref(0)
  const progress = shallowRef<Progress>({ phase: 'uploading', fraction: 0 })

  let source: { audio: Blob; filename: string } | null = null
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setInterval> | undefined

  function stopTimer() {
    clearInterval(timer)
    timer = undefined
  }

  async function start(audio: Blob, name: string) {
    cancel()
    source = { audio, filename: name }
    filename.value = name
    text.value = ''
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
        onProgress: (p) => {
          if (controller === ctrl) progress.value = p
        },
      })
      if (controller !== ctrl) return
      text.value = result
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
    if (source) void start(source.audio, source.filename)
  }

  function reset() {
    cancel()
    source = null
    status.value = 'idle'
    text.value = ''
    error.value = ''
    filename.value = ''
    elapsedSeconds.value = 0
  }

  onScopeDispose(cancel)

  return {
    status,
    text,
    error,
    filename,
    elapsedSeconds,
    progress,
    busy: computed(() => status.value === 'busy'),
    start,
    cancel,
    retry,
    reset,
  }
}
