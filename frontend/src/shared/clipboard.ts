/**
 * The single browser boundary for text copied by the application.
 *
 * Copy history will attach here later, so screens must not write to the
 * browser clipboard directly.
 */
export function copyText(text: string): Promise<void> {
  return navigator.clipboard.writeText(text)
}
