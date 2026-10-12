import { describe, expect, it } from 'vitest'
import type { Segment } from './transcriptionService'
import { baseName, docxBlob, speakerText, textBlob, timestamp, type SpeakerExport } from './exportService'

const segments: Segment[] = [
  { speaker: 'S1', start: 0, end: 12.4, text: 'Goedemorgen allemaal.' },
  { speaker: 'S2', start: 12.9, end: 31, text: ' Ja, ik heb een vraag. ' },
]
const names: Record<string, string> = { S2: 'Fatima' }
const exp = (options: SpeakerExport['options']): SpeakerExport => ({
  segments,
  label: (id) => names[id] ?? `Spreker ${id.slice(1)}`,
  options,
  durationSeconds: 31,
})

describe('baseName', () => {
  it('drops the extension and adds a suffix', () => {
    expect(baseName('overleg 12-10.m4a')).toBe('overleg 12-10-transcriptie')
  })

  it('replaces characters that are not allowed in file names', () => {
    expect(baseName('a/b:c?.mp3')).toBe('a_b_c_-transcriptie')
  })

  it('falls back when nothing is left', () => {
    expect(baseName('.mp3')).toBe('transcriptie-transcriptie')
  })
})

describe('textBlob', () => {
  it('writes UTF-8 with a BOM and Windows line endings', async () => {
    const bytes = new Uint8Array(await textBlob('één\ntwee').arrayBuffer())
    expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf])
    expect(new TextDecoder().decode(bytes.slice(3))).toBe('één\r\ntwee')
  })
})

describe('docxBlob', () => {
  it('produces a zip (docx) file', async () => {
    const blob = await docxBlob('Eerste alinea.\n\nTweede alinea.', 'Transcript test')
    const head = new Uint8Array(await blob.slice(0, 2).arrayBuffer())
    expect(String.fromCharCode(...head)).toBe('PK')
  })
})

describe('timestamp', () => {
  it('always has hours, minutes and seconds', () => {
    expect(timestamp(12.9)).toBe('00:00:12')
    expect(timestamp(3725)).toBe('01:02:05')
  })
})

describe('speakerText', () => {
  it('writes one turn per paragraph with time and name', () => {
    expect(speakerText(exp({ names: true, times: true }))).toBe(
      '[00:00:00] Spreker 1: Goedemorgen allemaal.\n\n[00:00:12] Fatima: Ja, ik heb een vraag.',
    )
  })

  it('leaves out what is switched off', () => {
    expect(speakerText(exp({ names: true, times: false }))).toBe(
      'Spreker 1: Goedemorgen allemaal.\n\nFatima: Ja, ik heb een vraag.',
    )
    expect(speakerText(exp({ names: false, times: false }))).toBe('Goedemorgen allemaal.\n\nJa, ik heb een vraag.')
  })
})

describe('docxBlob with speakers', () => {
  it('produces a docx as minutes and as a table', async () => {
    for (const table of [false, true]) {
      const blob = await docxBlob('', 'Transcript test', exp({ names: true, times: true, table }))
      const head = new Uint8Array(await blob.slice(0, 2).arrayBuffer())
      expect(String.fromCharCode(...head)).toBe('PK')
    }
  })
})
