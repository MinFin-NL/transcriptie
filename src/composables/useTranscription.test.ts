import { describe, expect, it, vi } from 'vitest'
import { TranscriptionError, type Transcript } from '../services/transcriptionService'
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
    const d = deferred<Transcript>()
    const t = useTranscription(() => d.promise)
    const run = t.start(audio, 'a.webm')
    expect(t.status.value).toBe('busy')
    expect(t.filename.value).toBe('a.webm')
    d.resolve({ text: 'Hallo' })
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
    const first = deferred<Transcript>()
    const second = deferred<Transcript>()
    const run = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const t = useTranscription(run)
    const a = t.start(audio, 'oud.webm')
    const b = t.start(audio, 'nieuw.webm')
    second.resolve({ text: 'nieuw' })
    await b
    first.resolve({ text: 'oud' })
    await a
    expect(t.text.value).toBe('nieuw')
    expect(t.filename.value).toBe('nieuw.webm')
  })

  it('keeps turns and lets the user name, merge and reassign speakers', async () => {
    const segments = [
      { speaker: 'S1', start: 0, end: 5, text: 'Goedemorgen.' },
      { speaker: 'S2', start: 5, end: 8, text: 'Hallo.' },
      { speaker: 'S3', start: 8, end: 9, text: 'Ja.' },
      { speaker: 'S1', start: 9, end: 12, text: 'Zullen we beginnen?' },
    ]
    let seen: unknown
    const t = useTranscription((_a, _f, opts) => {
      seen = opts?.speakers
      return Promise.resolve({ text: 'x', segments, durationSeconds: 12 })
    })
    await t.start(audio, 'a.webm', { enabled: true, count: 3 })
    expect(seen).toEqual({ enabled: true, count: 3 })
    expect(t.segments.value).toHaveLength(4)

    t.rename('S2', 'Fatima')
    expect(t.label('S2')).toBe('Fatima')
    expect(t.label('S1')).toBe('Spreker 1')

    // S3 is eigenlijk Fatima: haar twee beurten op rij worden één beurt.
    t.mergeSpeaker('S3', 'S2')
    expect(t.segments.value!.map((s) => [s.speaker, s.text])).toEqual([
      ['S1', 'Goedemorgen.'],
      ['S2', 'Hallo. Ja.'],
      ['S1', 'Zullen we beginnen?'],
    ])

    // De laatste beurt is ook van Fatima.
    t.reassign(2, 'S2')
    expect(t.segments.value!.map((s) => [s.speaker, s.end])).toEqual([
      ['S1', 5],
      ['S2', 12],
    ])

    t.editTurn(0, 'Goedemorgen allemaal.')
    expect(t.segments.value![0].text).toBe('Goedemorgen allemaal.')

    t.reset()
    expect(t.segments.value).toBeNull()
    expect(t.names.value).toEqual({})
  })
})
