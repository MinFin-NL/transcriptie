import { describe, expect, it, vi } from 'vitest'
import { TranscriptionError } from '../services/transcriptionService'
import { useTranscription } from './useTranscription'

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const audio = new Blob(['x'], { type: 'audio/webm' })

describe('useTranscription', () => {
  it('goes busy → done with the text', async () => {
    const d = deferred<string>()
    const t = useTranscription(() => d.promise)
    const run = t.start(audio, 'a.webm')
    expect(t.status.value).toBe('busy')
    expect(t.filename.value).toBe('a.webm')
    d.resolve('Hallo')
    await run
    expect(t.status.value).toBe('done')
    expect(t.text.value).toBe('Hallo')
  })

  it('shows the message of a TranscriptionError', async () => {
    const t = useTranscription(() => Promise.reject(new TranscriptionError('Te groot', 413)))
    await t.start(audio, 'a.webm')
    expect(t.status.value).toBe('error')
    expect(t.error.value).toBe('Te groot')
  })

  it('cancel aborts the request and returns to idle without an error', async () => {
    let signal: AbortSignal | undefined
    const t = useTranscription((_a, _f, opts) => {
      signal = opts?.signal
      return new Promise((_res, rej) =>
        signal!.addEventListener('abort', () => rej(new DOMException('aborted', 'AbortError'))),
      )
    })
    const run = t.start(audio, 'a.webm')
    t.cancel()
    await run
    expect(signal?.aborted).toBe(true)
    expect(t.status.value).toBe('idle')
    expect(t.error.value).toBe('')
  })

  it('retry sends the same audio again', async () => {
    const run = vi
      .fn()
      .mockRejectedValueOnce(new TranscriptionError('Druk', 429))
      .mockResolvedValueOnce('Gelukt')
    const t = useTranscription(run)
    await t.start(audio, 'a.webm')
    t.retry()
    await vi.waitFor(() => expect(t.status.value).toBe('done'))
    expect(run.mock.calls[1][0]).toBe(audio)
    expect(run.mock.calls[1][1]).toBe('a.webm')
  })

  it('ignores a stale result after a new start', async () => {
    const first = deferred<string>()
    const second = deferred<string>()
    const run = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const t = useTranscription(run)
    const a = t.start(audio, 'oud.webm')
    const b = t.start(audio, 'nieuw.webm')
    second.resolve('nieuw')
    await b
    first.resolve('oud')
    await a
    expect(t.text.value).toBe('nieuw')
    expect(t.filename.value).toBe('nieuw.webm')
  })
})
