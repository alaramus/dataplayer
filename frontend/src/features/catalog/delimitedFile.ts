import { t } from "@/shared/i18n"

const DELIMITERS = [",", ";", "\t", "|"] as const

export interface DelimitedFile {
  columns: string[]
  preview: string[][]
}

function delimiterOf(name: string, text: string): string {
  if (name.toLowerCase().endsWith(".tsv")) return "\t"
  const firstLine = text.split(/\r?\n/, 1)[0] ?? ""
  let quoted = false
  const counts = new Map(DELIMITERS.map((delimiter) => [delimiter, 0]))
  for (let index = 0; index < firstLine.length; index += 1) {
    const character = firstLine[index]
    if (character === '"') {
      if (quoted && firstLine[index + 1] === '"') index += 1
      else quoted = !quoted
    } else if (!quoted && counts.has(character as (typeof DELIMITERS)[number])) {
      const delimiter = character as (typeof DELIMITERS)[number]
      counts.set(delimiter, (counts.get(delimiter) ?? 0) + 1)
    }
  }
  return [...counts.entries()].sort((one, two) => two[1] - one[1])[0]?.[0] ?? ","
}

export function parseDelimited(text: string, name: string, previewRows = 20): DelimitedFile {
  const delimiter = delimiterOf(name, text)
  const records: string[][] = []
  let record: string[] = []
  let value = ""
  let quoted = false
  for (let index = 0; index <= text.length; index += 1) {
    const character = text[index]
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        value += '"'
        index += 1
      } else if (character === '"') quoted = false
      else if (character === undefined) throw new Error(t("catalog.file.unclosed_quote"))
      else value += character
      continue
    }
    if (character === '"' && value === "") quoted = true
    else if (character === delimiter) {
      record.push(value)
      value = ""
    } else if (character === "\n" || character === undefined) {
      if (character === undefined && value === "" && record.length === 0) break
      if (value.endsWith("\r")) value = value.slice(0, -1)
      record.push(value)
      records.push(record)
      record = []
      value = ""
      if (records.length > previewRows) break
    } else value += character
  }
  const header = records.shift()
  if (header === undefined || header.every((name) => name.trim() === "")) {
    throw new Error(t("catalog.file.no_header"))
  }
  const columns: string[] = []
  for (const [index, raw] of header.entries()) {
    let name = raw.trim() || `column_${index + 1}`
    if (columns.includes(name)) name = `${name}_${index + 1}`
    columns.push(name)
  }
  return {
    columns,
    preview: records.map((row) => columns.map((_, index) => row[index] ?? "")),
  }
}

/** How much of a file the form reads: its header and first rows are in there. */
const PREVIEW_BYTES = 1024 * 1024

/**
 * The columns and first rows of a file, read from its beginning only.
 *
 * Never the whole file: how large one may be is the server's to say, and a
 * file too large for one request is loaded by a job (D45). A row cut off at
 * the end of what was read is past the rows a preview shows.
 */
export async function readDelimited(file: File): Promise<DelimitedFile> {
  return parseDelimited(await textOf(file.slice(0, PREVIEW_BYTES)), file.name)
}

function textOf(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ""))
    reader.onerror = () => reject(reader.error ?? new Error("unreadable"))
    reader.readAsText(blob)
  })
}

export function filenameStem(name: string): string {
  const tail = name.replaceAll("\\", "/").split("/").at(-1) ?? name
  const at = tail.lastIndexOf(".")
  return at <= 0 ? tail : tail.slice(0, at)
}

/**
 * What the block of columns says about itself, in one line.
 *
 * It carries the reason Create is refused as well: a compact field keeps no
 * room under it for a message, and one line about the whole block beats the
 * same sentence repeated under four rows. Here rather than in the component
 * so the wording is tested without mounting a dialog that reads a catalog.
 */
export function columnTally(total: number, taken: number, unnamed: number): string {
  if (unnamed > 0) return t("catalog.file.unnamed", { n: unnamed }, unnamed)
  if (taken === 0) return t("catalog.file.none_of", { total })
  return taken === total ? t("catalog.file.all_of", { total }) : t("catalog.file.some_of", { taken, total })
}
