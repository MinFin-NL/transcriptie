import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { API, transcribe, TranscriptionError, type Progress } from './transcriptionService'

// Minimale XMLHttpRequest voor de upload: genoeg om status en body te sturen.
class FakeXhr {
  static next: { status: number; body: unknown } = { status: 202, body: {} }
  static last: FakeXhr | null = null
  upload = { onprogress: null as ((e: ProgressEvent) => void) | null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null
  status = 0
  responseText = ''
  responseType = ''
  method = ''
  url = ''
  sent: FormData | null = null

  open(method: string, url: string) {
    this.method = method
    this.url = url
  }

  send(body: FormData) {
    FakeXhr.last = this
    this.sent = body
    queueMicrotask(() => {
      this.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 } as ProgressEvent)
      this.status = FakeXhr.next.status
      this.responseText = JSON.stringify(FakeXhr.next.body)
      this.onload?.()
    })
  }

  abort() {
    this.onabort?.()
  }
}

const job = (over: object) => ({
  id: 'j1',
  status: 'queued',
  filename: 'a.mp3',
  durationSeconds: null,
  progress: { completed: 0, total: 0 },
  ...over,
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('XMLHttpRequest', FakeXhr)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('transcribe', () => {
  it('uploads, polls the job and returns the text, reporting progress', async () => {
    FakeXhr.next = { status: 202, body: job({}) }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(job({ status: 'transcribing', durationSeconds: 1800, progress: { completed: 1, total: 3 } })))
      .mockResolvedValueOnce(json(job({ status: 'done', text: ' Goedemorgen. ', progress: { completed: 3, total: 3 } })))
    vi.stubGlobal('fetch', fetchMock)

    const seen: Progress[] = []
    const run = transcribe(new Blob(['x']), 'overleg.mp3', { language: 'nl', onProgress: (p) => seen.push(p) })
    await vi.runAllTimersAsync()

    await expect(run).resolves.toBe('Goedemorgen.')
    expect(FakeXhr.last?.method).toBe('POST')
    expect(FakeXhr.last?.url).toBe(API)
    expect((FakeXhr.last?.sent?.get('file') as File).name).toBe('overleg.mp3')
    expect(FakeXhr.last?.sent?.get('language')).toBe('nl')
    expect(fetchMock.mock.calls[0][0]).toBe(`${API}/j1`)
    expect(seen).toContainEqual({ phase: 'uploading', fraction: 0.5 })
    expect(seen).toContainEqual({ phase: 'queued' })
    expect(seen).toContainEqual({ phase: 'transcribing', completed: 1, total: 3, durationSeconds: 1800 })
  })

  it('shows the problem detail of a rejected upload', async () => {
    FakeXhr.next = {
      status: 422,
      body: { status: 422, title: 'Opname te lang', detail: 'De opname duurt 150 minuten. Het maximum is 2 uur.' },
    }
    const run = transcribe(new Blob(['x']), 'lang.mp3').catch((e) => e)
    await vi.runAllTimersAsync()
    const err = await run
    expect(err).toBeInstanceOf(TranscriptionError)
    expect(err.status).toBe(422)
    expect(err.message).toBe('Opname te lang: De opname duurt 150 minuten. Het maximum is 2 uur.')
  })

  it('reports a failed job with its error', async () => {
    FakeXhr.next = { status: 202, body: job({}) }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(job({ status: 'failed', error: 'Dit bestand bevat geen geluid.' }))))
    const run = transcribe(new Blob(['x']), 'a.mp3').catch((e) => e)
    await vi.runAllTimersAsync()
    expect((await run).message).toBe('Dit bestand bevat geen geluid.')
  })

  it('cancelling while polling deletes the job on the server', async () => {
    FakeXhr.next = { status: 202, body: job({ status: 'transcribing', progress: { completed: 0, total: 2 } }) }
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const ctrl = new AbortController()
    const run = transcribe(new Blob(['x']), 'a.mp3', { signal: ctrl.signal }).catch((e) => e)
    await vi.advanceTimersByTimeAsync(0)
    ctrl.abort()
    const err = await run
    expect(err.name).toBe('AbortError')
    expect(fetchMock).toHaveBeenCalledWith(`${API}/j1`, { method: 'DELETE' })
  })

  it('cancelling during the upload aborts the request', async () => {
    const ctrl = new AbortController()
    ctrl.abort()
    await expect(transcribe(new Blob(['x']), 'a.mp3', { signal: ctrl.signal })).rejects.toMatchObject({
      name: 'AbortError',
    })
  })
})
