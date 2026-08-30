/**
 * The single browser boundary for text copied by the application.
 *
 * Copy history will attach here later, so screens must not write to the
 * browser clipboard directly.
 */
export function copyText(text: string): Promise<void> {
  return navigator.clipboard.writeText(text)
}

/**
 * Text the user is pasting, from the same boundary.
 *
 * A separate function rather than an argument to `copyText` because the
 * permission is a different one: reading the clipboard is a thing a browser
 * asks about and writing to it is not.
 */
export function readText(): Promise<string> {
  return navigator.clipboard.readText()
}
