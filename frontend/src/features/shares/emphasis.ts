/**
 * Names set in bold inside a translated sentence.
 *
 * A language puts a name wherever its sentence needs it, so the sentence is
 * one message and the names are marked as they go in rather than the message
 * being cut into pieces around them.
 */
const OPEN = "\u0002"
const CLOSE = "\u0003"

/** A parameter to be shown in bold. */
export function strong(value: string): string {
  return `${OPEN}${value}${CLOSE}`
}

export interface Part {
  text: string
  strong: boolean
}

/** A message with marked parameters, as runs of plain and bold text. */
export function emphasized(message: string): Part[] {
  const parts: Part[] = []
  for (const piece of message.split(OPEN)) {
    const close = piece.indexOf(CLOSE)
    if (close < 0) {
      if (piece !== "") parts.push({ text: piece, strong: false })
      continue
    }
    parts.push({ text: piece.slice(0, close), strong: true })
    const rest = piece.slice(close + 1)
    if (rest !== "") parts.push({ text: rest, strong: false })
  }
  return parts
}
