import { describe, expect, it } from 'vitest'
import { baseName, docxBlob, textBlob } from './exportService'

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
