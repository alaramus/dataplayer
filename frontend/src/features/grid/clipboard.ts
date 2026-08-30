/**
 * The grid's own TSV dialect, in both directions.
 *
 * Lossless on purpose: an unquoted empty field is nothing at all and a quoted
 * one is the empty string. Writing both as an empty field — which this did
 * until pasting existed — turns every empty string into a null on the way back,
 * and a copy that does not survive its own paste is not much of a copy.
 */

export function toTsv(matrix: readonly (readonly (string | null)[])[]): string {
  return matrix.map((row) => row.map(tsvCell).join("\t")).join("\r\n")
}

function tsvCell(value: string | null): string {
  if (value === null) return ""
  if (value !== "" && !/[\t\r\n"]/u.test(value)) return value
  return `"${value.replaceAll('"', '""')}"`
}

/**
 * A rectangle of cells read back out of clipboard text.
 *
 * Returns null for text that is not a rectangle — rows of differing widths —
 * because a block that is not one has no unambiguous landing place, and
 * guessing where the short rows stop is worse than saying so.
 *
 * Empty text is not a rectangle either: there is nothing to paste.
 */
export function fromTsv(text: string): (string | null)[][] | null {
  if (text === "") return null
  const rows = splitRows(text).map(splitCells)
  // A trailing newline is what a spreadsheet writes after the last row, not an
  // extra empty row.
  if (rows.length > 1 && rows.at(-1)?.length === 1 && rows.at(-1)?.[0] === null) {
    rows.pop()
  }
  const width = rows[0]?.length ?? 0
  if (width === 0) return null
  if (rows.some((row) => row.length !== width)) return null
  return rows
}

/** Split on line breaks that are not inside a quoted field. */
function splitRows(text: string): string[] {
  const rows: string[] = []
  let current = ""
  let quoted = false
  for (let at = 0; at < text.length; at += 1) {
    const char = text[at]
    if (char === '"') quoted = !quoted
    if (!quoted && (char === "\n" || char === "\r")) {
      rows.push(current)
      current = ""
      // \r\n is one break, not two.
      if (char === "\r" && text[at + 1] === "\n") at += 1
      continue
    }
    current += char
  }
  rows.push(current)
  return rows
}

function splitCells(row: string): (string | null)[] {
  const cells: (string | null)[] = []
  let current = ""
  let quoted = false
  let wasQuoted = false
  for (let at = 0; at < row.length; at += 1) {
    const char = row[at]
    if (char === '"') {
      if (quoted && row[at + 1] === '"') {
        current += '"'
        at += 1
        continue
      }
      quoted = !quoted
      wasQuoted = true
      continue
    }
    if (char === "\t" && !quoted) {
      cells.push(wasQuoted ? current : orNull(current))
      current = ""
      wasQuoted = false
      continue
    }
    current += char
  }
  cells.push(wasQuoted ? current : orNull(current))
  return cells
}

function orNull(value: string): string | null {
  return value === "" ? null : value
}
