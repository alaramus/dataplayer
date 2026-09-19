import type { ITheme } from "@xterm/xterm"

/**
 * The colours of a terminal's screen, read off the theme that is showing.
 *
 * xterm draws with colour values, not CSS, so the tokens are read out of the
 * page rather than named; the sixteen colours a shell asks for by number stay
 * xterm's own. Read again whenever the theme changes.
 */
export function screenTheme(element: HTMLElement): ITheme {
  const style = getComputedStyle(element)
  const foreground = style.color
  const background = style.getPropertyValue("--dp-surface").trim()
  const selection = style.getPropertyValue("--dp-text-selection").trim()
  return {
    foreground,
    background,
    cursor: foreground,
    cursorAccent: background,
    selectionBackground: selection,
  }
}
