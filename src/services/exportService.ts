// Exporteren van het transcript. Alles gebeurt in de browser: er gaat niets
// meer naar een server, ook de namen van sprekers niet.

import type { Segment } from './transcriptionService'

export interface SpeakerExportOptions {
  /** Sprekernaam voor elke beurt. */
  names: boolean
  /** Tijd voor elke beurt. */
  times: boolean
  /** .docx als tabel Tijd | Spreker | Tekst in plaats van een verslag. */
  table?: boolean
}

export interface SpeakerExport {
  segments: Segment[]
  label: (speaker: string) => string
  options: SpeakerExportOptions
  durationSeconds?: number | null
}

/** 12.4 → "00:00:12": vaste breedte, zodat tijden onder elkaar uitlijnen. */
export function timestamp(seconds: number): string {
  const t = Math.max(0, Math.floor(seconds))
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(Math.floor(t / 3600))}:${pad(Math.floor((t % 3600) / 60))}:${pad(t % 60)}`
}

/**
 * "[00:00:12] Fatima: Ja, ik heb …", met een witregel tussen beurten. Zo is
 * het goed te plakken in e-mail of Teams; kopiëren levert dezelfde tekst.
 */
export function speakerText({ segments, label, options }: SpeakerExport): string {
  return segments
    .map((s) => {
      const prefix = [options.times ? `[${timestamp(s.start)}]` : '', options.names ? `${label(s.speaker)}:` : '']
        .filter(Boolean)
        .join(' ')
      return prefix ? `${prefix} ${s.text.trim()}` : s.text.trim()
    })
    .join('\n\n')
}

/** Bestandsnaam zonder extensie, veilig voor elk besturingssysteem. */
export function baseName(source: string): string {
  const withoutExt = source.replace(/\.[^.]+$/, '')
  const safe = withoutExt.replace(/[\\/:*?"<>|]+/g, '_').trim()
  return `${safe || 'transcriptie'}-transcriptie`
}

/** UTF-8 met BOM, zodat Kladblok en Word de accenten goed lezen. */
export function textBlob(text: string): Blob {
  return new Blob(['﻿', text.replace(/\r?\n/g, '\r\n')], { type: 'text/plain;charset=utf-8' })
}

const DISCLAIMER = 'Automatisch gegenereerd transcript. Controleer de tekst voordat je hem gebruikt.'

export async function docxBlob(text: string, title: string, speakers?: SpeakerExport): Promise<Blob> {
  // Pas laden bij de eerste export: docx is groot en de meeste mensen kopiëren.
  const docx = await import('docx')
  const { Document, Packer, Paragraph, HeadingLevel } = docx

  const body = speakers ? speakerBody(docx, speakers) : plainBody(docx, text)
  const doc = new Document({
    creator: 'Transcriptie',
    title,
    styles: {
      // Word-stijlen in plaats van losse opmaak: wie het verslag in de eigen
      // huisstijl wil, past één stijl aan.
      paragraphStyles: [
        {
          id: 'Spreker',
          name: 'Spreker',
          basedOn: 'Normal',
          next: 'Beurt',
          run: { bold: true },
          paragraph: { spacing: { before: 240, after: 40 }, keepNext: true },
        },
        { id: 'Beurt', name: 'Beurt', basedOn: 'Normal', next: 'Spreker' },
      ],
      characterStyles: [{ id: 'Tijd', name: 'Tijd', run: { color: '666666', bold: false } }],
    },
    sections: [
      {
        children: [
          new Paragraph({ text: title, heading: HeadingLevel.HEADING_1 }),
          ...(speakers ? details(docx, speakers) : []),
          new Paragraph({ text: DISCLAIMER, style: 'Quote' }),
          ...body,
        ],
      },
    ],
  })
  return Packer.toBlob(doc)
}

type Docx = typeof import('docx')

function plainBody({ Paragraph }: Docx, text: string) {
  return text
    .split(/\n\s*\n|\r\n\s*\r\n/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => new Paragraph({ text: p.replace(/\s*\n\s*/g, ' ') }))
}

/** Kop met gegevens: wanneer gemaakt, hoe lang, wie er spraken. */
function details({ Paragraph, TextRun }: Docx, { segments, label, durationSeconds }: SpeakerExport) {
  const names = [...new Set(segments.map((s) => s.speaker))].map(label)
  const rows: [string, string][] = [
    ['Gemaakt op', new Date().toLocaleDateString('nl-NL', { day: 'numeric', month: 'long', year: 'numeric' })],
    ...(durationSeconds ? [['Duur', timestamp(durationSeconds)] as [string, string]] : []),
    ['Sprekers', names.join(', ')],
  ]
  return rows.map(
    ([k, v]) => new Paragraph({ children: [new TextRun({ text: `${k}\t`, bold: true }), new TextRun(v)] }),
  )
}

function speakerBody(docx: Docx, { segments, label, options }: SpeakerExport) {
  const { Paragraph, TextRun, Table, TableRow, TableCell, WidthType } = docx
  if (options.table) {
    const cell = (text: string, bold = false) =>
      new TableCell({ children: [new Paragraph({ children: [new TextRun({ text, bold })] })] })
    const head = [options.times && 'Tijd', options.names && 'Spreker', 'Tekst'].filter(Boolean) as string[]
    return [
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        rows: [
          new TableRow({ tableHeader: true, children: head.map((h) => cell(h, true)) }),
          ...segments.map(
            (s) =>
              new TableRow({
                children: [
                  ...(options.times ? [cell(timestamp(s.start))] : []),
                  ...(options.names ? [cell(label(s.speaker))] : []),
                  cell(s.text.trim()),
                ],
              }),
          ),
        ],
      }),
    ]
  }
  return segments.flatMap((s) => {
    const heading = [
      ...(options.names ? [new TextRun(label(s.speaker))] : []),
      ...(options.times ? [new TextRun({ text: `${options.names ? '  ' : ''}${timestamp(s.start)}`, style: 'Tijd' })] : []),
    ]
    return [
      ...(heading.length ? [new Paragraph({ style: 'Spreker', children: heading })] : []),
      new Paragraph({ style: 'Beurt', text: s.text.trim() }),
    ]
  })
}

export function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.append(a)
  a.click()
  a.remove()
  // Even laten staan: sommige browsers lezen de URL pas na de klik.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
