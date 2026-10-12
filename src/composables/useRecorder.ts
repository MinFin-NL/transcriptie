import { onScopeDispose, ref, shallowRef } from 'vue'

export type RecorderState = 'idle' | 'requesting' | 'recording' | 'stopped' | 'error'

// Volgorde van voorkeur. Chrome en Firefox kunnen webm/opus, Safari alleen mp4.
// De backend zet alles met ffmpeg om naar 16 kHz mono wav.
const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']

// Spraak heeft genoeg aan 32 kbit/s; zo past ruim een uur binnen 25 MB.
const BITS_PER_SECOND = 32_000

export function pickMimeType(isSupported: (type: string) => boolean): string {
  return MIME_TYPES.find((t) => isSupported(t)) ?? ''
}

export function extensionFor(mimeType: string): string {
  if (mimeType.includes('mp4')) return 'm4a'
  if (mimeType.includes('ogg')) return 'ogg'
  return 'webm'
}

export function isRecordingSupported(): boolean {
  return typeof window !== 'undefined' && 'MediaRecorder' in window && !!navigator.mediaDevices?.getUserMedia
}

/**
 * Neemt op via de microfoon en levert bij stoppen één Blob op. Opnemen kan
 * alleen in een veilige context (https of localhost).
 */
export function useRecorder() {
  const state = ref<RecorderState>('idle')
  const error = ref('')
  const elapsedSeconds = ref(0)
  const recording = shallowRef<Blob | null>(null)
  const recordingUrl = ref('')

  let recorder: MediaRecorder | null = null
  let stream: MediaStream | null = null
  let chunks: Blob[] = []
  let timer: ReturnType<typeof setInterval> | undefined

  function releaseStream() {
    stream?.getTracks().forEach((t) => t.stop())
    stream = null
    clearInterval(timer)
    timer = undefined
  }

  function clearRecording() {
    if (recordingUrl.value) URL.revokeObjectURL(recordingUrl.value)
    recordingUrl.value = ''
    recording.value = null
  }

  async function start() {
    clearRecording()
    error.value = ''
    state.value = 'requesting'
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err) {
      state.value = 'error'
      const name = err instanceof DOMException ? err.name : ''
      error.value =
        name === 'NotAllowedError'
          ? 'Je browser geeft geen toegang tot de microfoon. Sta de microfoon toe in de adresbalk en probeer het opnieuw.'
          : name === 'NotFoundError'
            ? 'Er is geen microfoon gevonden. Sluit een microfoon aan en probeer het opnieuw.'
            : 'De microfoon kan niet worden gestart.'
      return
    }

    const mimeType = pickMimeType((t) => MediaRecorder.isTypeSupported(t))
    recorder = new MediaRecorder(stream, {
      ...(mimeType ? { mimeType } : {}),
      audioBitsPerSecond: BITS_PER_SECOND,
    })
    chunks = []
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data)
    }
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: recorder?.mimeType || mimeType || 'audio/webm' })
      chunks = []
      recording.value = blob
      recordingUrl.value = URL.createObjectURL(blob)
      state.value = 'stopped'
      releaseStream()
    }

    // Elke seconde een stuk, zodat een lange opname niet in één keer in het
    // geheugen hoeft te worden opgebouwd bij het stoppen.
    recorder.start(1000)
    state.value = 'recording'
    elapsedSeconds.value = 0
    const started = Date.now()
    timer = setInterval(() => {
      elapsedSeconds.value = Math.floor((Date.now() - started) / 1000)
    }, 1000)
  }

  function stop() {
    if (recorder && recorder.state !== 'inactive') recorder.stop()
  }

  function discard() {
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = null
      recorder.stop()
    }
    recorder = null
    chunks = []
    releaseStream()
    clearRecording()
    elapsedSeconds.value = 0
    state.value = 'idle'
  }

  onScopeDispose(discard)

  return { state, error, elapsedSeconds, recording, recordingUrl, start, stop, discard }
}
