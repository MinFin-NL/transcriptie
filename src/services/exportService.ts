// Exporteren van het transcript. Alles gebeurt in de browser: er gaat niets
// meer naar een server.

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

export async function docxBlob(text: string, title: string): Promise<Blob> {
  // Pas laden bij de eerste export: docx is groot en de meeste mensen kopiëren.
  const { Document, Packer, Paragraph, HeadingLevel } = await import('docx')
  const paragraphs = text
    .split(/\n\s*\n|\r\n\s*\r\n/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => new Paragraph({ text: p.replace(/\s*\n\s*/g, ' ') }))

  const doc = new Document({
    creator: 'Transcriptie',
    title,
    sections: [
      {
        children: [
          new Paragraph({ text: title, heading: HeadingLevel.HEADING_1 }),
          new Paragraph({
            text: 'Automatisch gegenereerd transcript. Controleer de tekst voordat je hem gebruikt.',
            style: 'Quote',
          }),
          ...paragraphs,
        ],
      },
    ],
  })
  return Packer.toBlob(doc)
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
