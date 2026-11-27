import type { CopyCreate } from "@/client"

/**
 * Where a copy came from (D460). Required, so every copy button decides: a
 * secret is never kept in the copy history, a copy taken from the history
 * itself is already there and is not kept again, and anything else names the
 * place it was copied from.
 */
export type CopyOrigin =
  | { from: CopyCreate["source"]; detail?: string | null }
  | { secret: true }
  | { history: true }

export type CopyListener = (text: string, origin: Extract<CopyOrigin, { from: unknown }>) => void

let listener: CopyListener | null = null

/**
 * Who hears of a copy that is not a secret: the copy history, installed once
 * at start-up. A setter rather than an import of the feature, so this module
 * stays below every screen that copies.
 */
export function onCopied(next: CopyListener | null): void {
  listener = next
}

/** The single browser boundary for text copied by the application. */
export async function copyText(text: string, origin: CopyOrigin): Promise<void> {
  // `navigator.clipboard` exists only in a secure context; a page served over
  // plain HTTP to another machine copies through a selection instead.
  if (navigator.clipboard) await navigator.clipboard.writeText(text)
  else copyThroughSelection(text)
  if (listener !== null && "from" in origin && text !== "") listener(text, origin)
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
