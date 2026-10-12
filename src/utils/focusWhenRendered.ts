/**
 * Zet de focus op `el`, ook als het in een NLDD-component staat dat nog niet
 * gerenderd is. Lit rendert de shadow DOM asynchroon; tot dat gebeurt heeft
 * een geslot element geen plek in de layout en negeert de browser focus().
 * Daarom proberen we het een paar frames lang opnieuw.
 */
export function focusWhenRendered(el: HTMLElement | null | undefined, frames = 20): void {
  if (!el) return
  el.focus({ preventScroll: false })
  if (document.activeElement === el || frames <= 0) return
  requestAnimationFrame(() => focusWhenRendered(el, frames - 1))
}
