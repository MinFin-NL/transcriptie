/**
 * Duur van een audiobestand in seconden, gelezen door de browser zelf.
 * `null` als de browser het niet weet: sommige formaten (webm uit
 * MediaRecorder bijvoorbeeld) hebben geen duur in de header. De backend meet
 * dan na het omzetten en weigert alsnog als het te lang is.
 */
export function audioDuration(file: Blob, timeoutMs = 5000): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const el = new Audio()
    const done = (value: number | null) => {
      clearTimeout(timer)
      el.removeAttribute('src')
      el.load()
      URL.revokeObjectURL(url)
      resolve(value)
    }
    const timer = setTimeout(() => done(null), timeoutMs)
    el.preload = 'metadata'
    el.onloadedmetadata = () => done(Number.isFinite(el.duration) && el.duration > 0 ? el.duration : null)
    el.onerror = () => done(null)
    el.src = url
  })
}
