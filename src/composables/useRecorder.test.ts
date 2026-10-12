import { describe, expect, it } from 'vitest'
import { extensionFor, pickMimeType } from './useRecorder'

describe('pickMimeType', () => {
  it('prefers webm/opus', () => {
    expect(pickMimeType(() => true)).toBe('audio/webm;codecs=opus')
  })

  it('falls back to mp4 on Safari', () => {
    expect(pickMimeType((t) => t === 'audio/mp4')).toBe('audio/mp4')
  })

  it('returns empty when nothing is supported, so the browser picks', () => {
    expect(pickMimeType(() => false)).toBe('')
  })
})

describe('extensionFor', () => {
  it.each([
    ['audio/webm;codecs=opus', 'webm'],
    ['audio/mp4', 'm4a'],
    ['audio/ogg;codecs=opus', 'ogg'],
  ])('%s → %s', (mime, ext) => {
    expect(extensionFor(mime)).toBe(ext)
  })
})
