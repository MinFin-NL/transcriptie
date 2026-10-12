// Beurten bewerken in de browser: sprekers samenvoegen, een beurt aan een
// ander geven. Pure functies; namen en beurten gaan nooit terug naar de server.

import type { Segment } from '../services/transcriptionService'

export type Names = Record<string, string>

/** "Spreker 3" voor S3, of de naam die de gebruiker gaf. */
export function speakerLabel(id: string, names: Names = {}): string {
  const name = names[id]?.trim()
  if (name) return name
  const n = /^S(\d+)$/.exec(id)?.[1]
  return n ? `Spreker ${n}` : id
}

/** Sprekers in volgorde van eerste keer spreken. */
export function speakerIds(segments: Segment[]): string[] {
  return [...new Set(segments.map((s) => s.speaker))]
}

/** Opeenvolgende beurten van dezelfde spreker worden één beurt. */
export function mergeAdjacent(segments: Segment[]): Segment[] {
  const out: Segment[] = []
  for (const seg of segments) {
    const last = out[out.length - 1]
    if (last && last.speaker === seg.speaker) {
      out[out.length - 1] = { ...last, end: Math.max(last.end, seg.end), text: joinText(last.text, seg.text) }
    } else {
      out.push({ ...seg })
    }
  }
  return out
}

/** Alle beurten van `from` horen voortaan bij `into`. */
export function mergeSpeakers(segments: Segment[], from: string, into: string): Segment[] {
  return mergeAdjacent(segments.map((s) => (s.speaker === from ? { ...s, speaker: into } : s)))
}

/** Eén beurt aan een andere spreker geven. */
export function reassignTurn(segments: Segment[], index: number, speaker: string): Segment[] {
  return mergeAdjacent(segments.map((s, i) => (i === index ? { ...s, speaker } : s)))
}

export interface SpeakerStats {
  turns: number
  seconds: number
}

export function speakerStats(segments: Segment[]): Record<string, SpeakerStats> {
  const stats: Record<string, SpeakerStats> = {}
  for (const s of segments) {
    const st = (stats[s.speaker] ??= { turns: 0, seconds: 0 })
    st.turns += 1
    st.seconds += Math.max(0, s.end - s.start)
  }
  return stats
}

function joinText(a: string, b: string): string {
  return [a.trim(), b.trim()].filter(Boolean).join(' ')
}
