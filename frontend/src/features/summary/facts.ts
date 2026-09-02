import type { NodeSummary } from "@/client"
import { formatSize } from "@/features/catalog/nodes"
import { formatDuration, mediaTypeName } from "@/features/content/media"
import { datasetFacts } from "@/features/structure/model"

/** What a format states about itself, as the source sent it (D75). */
export type NodeContents = NonNullable<NodeSummary["contents"]>

export interface Fact {
  label: string
  value: string
}

export interface Described {
  /** What every node has: how big, since when, what it opens as. */
  facts: Fact[]
  /** What this one's format states, which is empty for a format that states nothing. */
  contents: Fact[]
  /** Why something above is missing: a refused format, or a count that hit a ceiling. */
  notice: string | null
}

const KINDS: Record<NodeSummary["kind"], string> = {
  schema: "Schema",
  table: "Table",
  view: "View",
  directory: "Folder",
  file: "File",
  dataset: "Dataset",
  entry: "Archive entry",
  report: "Report",
}

const ENCODINGS: Record<"utf-8" | "utf-8-bom" | "not-utf-8", string> = {
  "utf-8": "UTF-8",
  "utf-8-bom": "UTF-8 with a byte order mark",
  "not-utf-8": "Not UTF-8",
}

const ENDINGS: Record<"lf" | "crlf" | "cr" | "mixed" | "none", string> = {
  lf: "LF (Unix)",
  crlf: "CRLF (Windows)",
  cr: "CR (classic Mac)",
  mixed: "Mixed",
  none: "None",
}

/**
 * One node's answer, turned into lines to print.
 *
 * Pure, so the wording is tested without mounting anything, and one entry
 * point, so the panel never reaches into the union itself. Absent is absent:
 * a time the platform does not state and a count that hit a ceiling both leave
 * their line out, rather than printing a zero that reads as a measurement.
 */
export function describe(summary: NodeSummary): Described {
  const contents = summary.contents ?? null
  return {
    facts: nodeFacts(summary),
    contents: contents === null ? [] : contentsFacts(contents),
    notice: summary.notice ?? (contents === null ? null : notCounted(contents)),
  }
}

function nodeFacts(summary: NodeSummary): Fact[] {
  const facts: Fact[] = [{ label: "Kind", value: KINDS[summary.kind] }]
  if (summary.size_bytes !== null && summary.size_bytes !== undefined) {
    facts.push({ label: "Size", value: formatSize(summary.size_bytes) })
  }
  addMoment(facts, "Modified", summary.modified_at)
  addMoment(facts, "Created", summary.created_at)
  addMoment(facts, "Opened", summary.accessed_at)
  if (summary.permissions !== null && summary.permissions !== undefined) {
    facts.push({ label: "Permissions", value: summary.permissions })
  }
  // A folder is walked into rather than opened, so it is not asked what it
  // opens as; anything else says so even when the answer is nothing.
  if (summary.kind !== "directory") {
    const opens = (summary.representations ?? []).map((item) => item.title)
    facts.push({
      label: "Opens as",
      value: opens.length > 0 ? opens.join(", ") : "Nothing this source can show",
    })
  }
  return facts
}

function addMoment(facts: Fact[], label: string, moment: string | null | undefined) {
  if (moment === null || moment === undefined) return
  facts.push({ label, value: new Date(moment).toLocaleString() })
}

/**
 * The format's own facts.
 *
 * The switch is exhaustive: a format added to the union on the server is a
 * type error here until somebody decides what a reader should be told about
 * it — the reason the facts travel as a union rather than as pairs of strings
 * the source wrote. Two of its members are a dataset's, and are printed by the
 * function that already prints one.
 */
function contentsFacts(contents: NodeContents): Fact[] {
  switch (contents.kind) {
    case "text": {
      const facts: Fact[] = [
        { label: "Encoding", value: ENCODINGS[contents.encoding] },
      ]
      addCount(facts, "Lines", contents.lines)
      if (contents.longest_line_bytes !== null && contents.longest_line_bytes !== undefined) {
        facts.push({
          label: "Longest line",
          value: formatSize(contents.longest_line_bytes),
        })
      }
      if (contents.line_endings !== null && contents.line_endings !== undefined) {
        facts.push({ label: "Line endings", value: ENDINGS[contents.line_endings] })
      }
      return facts
    }
    case "delimited": {
      const facts: Fact[] = []
      if (contents.delimiter !== null && contents.delimiter !== undefined) {
        facts.push({ label: "Separated by", value: contents.delimiter })
      }
      addCount(facts, "Columns", contents.columns)
      addCount(facts, "Rows", contents.rows)
      facts.push({ label: "Encoding", value: ENCODINGS[contents.encoding] })
      return facts
    }
    case "parquet":
    case "worksheet":
      return datasetFacts(contents)
    case "workbook": {
      const facts: Fact[] = [{ label: "Sheets", value: String(contents.sheets) }]
      if (contents.hidden_sheets > 0) {
        facts.push({ label: "Hidden sheets", value: String(contents.hidden_sheets) })
      }
      return facts
    }
    case "archive": {
      const facts: Fact[] = [
        { label: "Entries", value: String(contents.entries) },
        { label: "Files", value: String(contents.files) },
        { label: "Folders", value: String(contents.directories) },
        { label: "Unpacked", value: formatSize(contents.size_bytes) },
        { label: "Packed", value: formatSize(contents.compressed_bytes) },
      ]
      if (contents.encrypted > 0) {
        facts.push({ label: "Encrypted entries", value: String(contents.encrypted) })
      }
      if (contents.links > 0) {
        facts.push({ label: "Links", value: String(contents.links) })
      }
      return facts
    }
    case "entry": {
      const facts: Fact[] = []
      if (contents.compressed_bytes !== null && contents.compressed_bytes !== undefined) {
        facts.push({ label: "Packed", value: formatSize(contents.compressed_bytes) })
      }
      // Both are why an entry cannot be read, so they are shown only when they
      // are the answer to that (D53).
      if (contents.encrypted === true) facts.push({ label: "Encrypted", value: "Yes" })
      if (contents.link === true) facts.push({ label: "Link", value: "Yes" })
      return facts
    }
    case "image":
      return [
        { label: "Format", value: mediaTypeName(contents.media_type) },
        { label: "Size", value: `${String(contents.width)} × ${String(contents.height)}` },
      ]
    case "audio": {
      const facts: Fact[] = [
        { label: "Format", value: mediaTypeName(contents.media_type) },
      ]
      addDuration(facts, contents.duration_seconds)
      addCount(facts, "Channels", contents.channels)
      if (contents.sample_rate !== null && contents.sample_rate !== undefined) {
        facts.push({
          label: "Sample rate",
          value: `${String(contents.sample_rate / 1000)} kHz`,
        })
      }
      return facts
    }
    case "video": {
      const facts: Fact[] = [
        { label: "Format", value: mediaTypeName(contents.media_type) },
      ]
      addDuration(facts, contents.duration_seconds)
      if (contents.width && contents.height) {
        facts.push({
          label: "Size",
          value: `${String(contents.width)} × ${String(contents.height)}`,
        })
      }
      return facts
    }
    case "pdf":
      return [{ label: "Format", value: `PDF ${contents.version}` }]
    case "directory": {
      const facts: Fact[] = []
      addCount(facts, "Entries", contents.entries)
      addCount(facts, "Files", contents.files)
      addCount(facts, "Folders", contents.directories)
      return facts
    }
    default:
      return unknownContents(contents)
  }
}

/** Why a count is missing, for the members that can hit a ceiling. */
function notCounted(contents: NodeContents): string | null {
  if (contents.kind === "text" || contents.kind === "delimited" || contents.kind === "directory") {
    return contents.not_counted ?? null
  }
  return null
}

function addCount(facts: Fact[], label: string, count: number | null | undefined) {
  if (count === null || count === undefined) return
  facts.push({ label, value: String(count) })
}

function addDuration(facts: Fact[], seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return
  facts.push({ label: "Duration", value: formatDuration(seconds) })
}

function unknownContents(contents: never): never {
  throw new Error(`Unknown contents: ${JSON.stringify(contents)}`)
}
