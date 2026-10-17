/**
 * The single browser boundary for text copied by the application.
 *
 * Copy history will attach here later, so screens must not write to the
 * browser clipboard directly.
 */
export async function copyText(text: string): Promise<void> {
  // `navigator.clipboard` exists only in a secure context; a page served over
  // plain HTTP to another machine copies through a selection instead.
  if (navigator.clipboard) return navigator.clipboard.writeText(text)
  copyThroughSelection(text)
}

/**
 * Text the user is pasting, from the same boundary.
 *
 * A separate function rather than an argument to `copyText` because the
 * permission is a different one: reading the clipboard is a thing a browser
 * asks about and writing to it is not. Outside a secure context there is no
 * way to read it at all, and this rejects with `ClipboardUnavailable`.
 */
export async function readText(): Promise<string> {
  if (!navigator.clipboard) throw new ClipboardUnavailable()
  return navigator.clipboard.readText()
}

/** The page is not a secure context, so the browser keeps the clipboard from it. */
export class ClipboardUnavailable extends Error {
  constructor() {
    super("The clipboard is available only over HTTPS")
    this.name = "ClipboardUnavailable"
  }
}

function copyThroughSelection(text: string): void {
  const area = document.createElement("textarea")
  area.value = text
  area.setAttribute("readonly", "")
  area.style.position = "fixed"
  area.style.opacity = "0"
  document.body.appendChild(area)
  const focused = document.activeElement
  area.focus()
  area.select()
  try {
    // Deprecated, and the only copy a browser allows outside a secure context.
    if (!document.execCommand("copy")) throw new Error("The browser refused to copy")
  } finally {
    area.remove()
    if (focused instanceof HTMLElement) focused.focus()
  }
}
