import type { NodeSummary, RelationContents } from "@/client"
import { formatSize } from "@/features/catalog/nodes"
import { formatDuration, mediaTypeName } from "@/features/content/media"
import { datasetFacts } from "@/features/structure/model"
import { statisticsFacts } from "@/features/summary/timescaleStatistics"
import { t } from "@/shared/i18n"
import type { MessageKey } from "@/shared/i18n"

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

const ENCODINGS: Record<"utf-8" | "utf-8-bom" | "not-utf-8", MessageKey> = {
  "utf-8": "summary.encodings.utf_8",
  "utf-8-bom": "summary.encodings.utf_8_bom",
  "not-utf-8": "summary.encodings.not_utf_8",
}

/** A relation as stored, where that is not what the "Kind" line already says. */
type RelationKind = Extract<NodeContents, { kind: "relation" }>["relation_kind"]

const STORED_AS: Partial<Record<RelationKind, MessageKey>> = {
  partitioned_table: "summary.stored_as.partitioned_table",
  materialized_view: "summary.stored_as.materialized_view",
  foreign_table: "summary.stored_as.foreign_table",
}

function yesNo(value: boolean): string {
  return value ? t("summary.yes") : t("summary.no")
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
  const facts: Fact[] = [{ label: t("summary.facts.kind"), value: t(`summary.kinds.${summary.kind}`) }]
  if (summary.size_bytes !== null && summary.size_bytes !== undefined) {
    facts.push({ label: t("summary.facts.size"), value: formatSize(summary.size_bytes) })
  }
  addMoment(facts, t("summary.facts.modified"), summary.modified_at)
  addMoment(facts, t("summary.facts.created"), summary.created_at)
  addMoment(facts, t("summary.facts.opened"), summary.accessed_at)
  if (summary.permissions !== null && summary.permissions !== undefined) {
    facts.push({ label: t("summary.facts.permissions"), value: summary.permissions })
  }
  // A folder is walked into rather than opened, so it is not asked what it
  // opens as; anything else says so even when the answer is nothing.
  if (summary.kind !== "directory") {
    const opens = (summary.representations ?? []).map((item) => item.title)
    facts.push({
      label: t("summary.facts.opens_as"),
      value: opens.length > 0 ? opens.join(", ") : t("summary.values.opens_nothing"),
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
        { label: t("summary.facts.encoding"), value: t(ENCODINGS[contents.encoding]) },
      ]
      addCount(facts, t("summary.facts.lines"), contents.lines)
      if (contents.longest_line_bytes !== null && contents.longest_line_bytes !== undefined) {
        facts.push({
          label: t("summary.facts.longest_line"),
          value: formatSize(contents.longest_line_bytes),
        })
      }
      if (contents.line_endings !== null && contents.line_endings !== undefined) {
        facts.push({ label: t("summary.facts.line_endings"), value: t(`summary.endings.${contents.line_endings}`) })
      }
      return facts
    }
    case "delimited": {
      const facts: Fact[] = []
      if (contents.delimiter !== null && contents.delimiter !== undefined) {
        facts.push({ label: t("summary.facts.separated_by"), value: contents.delimiter })
      }
      addCount(facts, t("summary.facts.columns"), contents.columns)
      addCount(facts, t("summary.facts.rows"), contents.rows)
      facts.push({ label: t("summary.facts.encoding"), value: t(ENCODINGS[contents.encoding]) })
      return facts
    }
    case "parquet":
    case "worksheet":
      return datasetFacts(contents)
    case "workbook": {
      const facts: Fact[] = [{ label: t("summary.facts.sheets"), value: String(contents.sheets) }]
      if (contents.hidden_sheets > 0) {
        facts.push({ label: t("summary.facts.hidden_sheets"), value: String(contents.hidden_sheets) })
      }
      return facts
    }
    case "archive": {
      const facts: Fact[] = [
        { label: t("summary.facts.entries"), value: String(contents.entries) },
        { label: t("summary.facts.files"), value: String(contents.files) },
        { label: t("summary.facts.folders"), value: String(contents.directories) },
        { label: t("summary.facts.unpacked"), value: formatSize(contents.size_bytes) },
        { label: t("summary.facts.packed"), value: formatSize(contents.compressed_bytes) },
      ]
      if (contents.encrypted > 0) {
        facts.push({ label: t("summary.facts.encrypted_entries"), value: String(contents.encrypted) })
      }
      if (contents.links > 0) {
        facts.push({ label: t("summary.facts.links"), value: String(contents.links) })
      }
      return facts
    }
    case "entry": {
      const facts: Fact[] = []
      if (contents.compressed_bytes !== null && contents.compressed_bytes !== undefined) {
        facts.push({ label: t("summary.facts.packed"), value: formatSize(contents.compressed_bytes) })
      }
      // Both are why an entry cannot be read, so they are shown only when they
      // are the answer to that (D53).
      if (contents.encrypted === true) facts.push({ label: t("summary.facts.encrypted"), value: yesNo(true) })
      if (contents.link === true) facts.push({ label: t("summary.facts.link"), value: yesNo(true) })
      return facts
    }
    case "image":
      return [
        { label: t("summary.facts.format"), value: mediaTypeName(contents.media_type) },
        { label: t("summary.facts.size"), value: `${String(contents.width)} × ${String(contents.height)}` },
      ]
    case "audio": {
      const facts: Fact[] = [
        { label: t("summary.facts.format"), value: mediaTypeName(contents.media_type) },
      ]
      addDuration(facts, contents.duration_seconds)
      addCount(facts, t("summary.facts.channels"), contents.channels)
      if (contents.sample_rate !== null && contents.sample_rate !== undefined) {
        facts.push({
          label: t("summary.facts.sample_rate"),
          value: t("summary.values.khz", { n: contents.sample_rate / 1000 }),
        })
      }
      return facts
    }
    case "video": {
      const facts: Fact[] = [
        { label: t("summary.facts.format"), value: mediaTypeName(contents.media_type) },
      ]
      addDuration(facts, contents.duration_seconds)
      if (contents.width && contents.height) {
        facts.push({
          label: t("summary.facts.size"),
          value: `${String(contents.width)} × ${String(contents.height)}`,
        })
      }
      return facts
    }
    case "pdf":
      return [{ label: t("summary.facts.format"), value: `PDF ${contents.version}` }]
    case "directory": {
      const facts: Fact[] = []
      addCount(facts, t("summary.facts.entries"), contents.entries)
      addCount(facts, t("summary.facts.files"), contents.files)
      addCount(facts, t("summary.facts.folders"), contents.directories)
      return facts
    }
    case "relation": {
      const facts: Fact[] = []
      if (contents.specialization) {
        facts.push({
          label: t("summary.facts.specialization"),
          value:
            contents.specialization.kind === "timescale_hypertable"
              ? t("summary.values.hypertable")
              : t("summary.values.continuous_aggregate"),
        })
      }
      if (contents.timescale) facts.push(...timescaleFacts(contents.timescale))
      if (contents.timescale_statistics) {
        facts.push(...statisticsFacts(
          contents.timescale_statistics,
          contents.specialization?.kind === "timescale_continuous_aggregate",
        ))
      }
      // Only where it says something the "Kind" line above does not: there a
      // table is a table and a materialized view is only a view.
      const stored = STORED_AS[contents.relation_kind]
      if (stored !== undefined) facts.push({ label: t("summary.facts.stored_as"), value: t(stored) })
      facts.push({ label: t("summary.facts.schema"), value: contents.schema_name })
      if (contents.owner !== null && contents.owner !== undefined) {
        facts.push({ label: t("summary.facts.owner"), value: contents.owner })
      }
      // A permanent table is every table, and a line saying so on all of them
      // would say nothing on any of them.
      if (
        contents.persistence !== null &&
        contents.persistence !== undefined &&
        contents.persistence !== "permanent"
      ) {
        facts.push({ label: t("summary.facts.storage"), value: t(`summary.persistence.${contents.persistence}`) })
      }
      addCount(facts, t("summary.facts.columns"), contents.columns)
      addCount(facts, t("summary.facts.indexes"), contents.indexes)
      addCount(facts, t("summary.facts.constraints"), contents.constraints)
      // Said even when there is no number, as it is in the catalog: a missing
      // line reads as one nobody filled in rather than as a count nobody has.
      facts.push({
        label: t("summary.facts.rows"),
        value:
          contents.row_estimate === null || contents.row_estimate === undefined
            ? t("summary.values.not_estimated")
            : t("summary.values.estimate", { n: contents.row_estimate }),
      })
      if (contents.partitioned_by !== null && contents.partitioned_by !== undefined) {
        facts.push({ label: t("summary.facts.partitioned_by"), value: contents.partitioned_by })
      }
      if (contents.partition_of !== null && contents.partition_of !== undefined) {
        facts.push({ label: t("summary.facts.partition_of"), value: contents.partition_of })
      }
      addMoment(facts, t("summary.facts.analysed"), contents.analyzed_at)
      addMoment(facts, t("summary.facts.vacuumed"), contents.vacuumed_at)
      if (contents.comment !== null && contents.comment !== undefined) {
        facts.push({ label: t("summary.facts.comment"), value: contents.comment })
      }
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
  facts.push({ label: t("summary.facts.duration"), value: formatDuration(seconds) })
}

function unknownContents(contents: never): never {
  throw new Error(`Unknown contents: ${JSON.stringify(contents)}`)
}

function timescaleFacts(details: NonNullable<RelationContents["timescale"]>): Fact[] {
  switch (details.kind) {
    case "hypertable":
      return [
        { label: t("summary.facts.dimensions"), value: String(details.num_dimensions) },
        { label: t("summary.facts.chunks"), value: details.num_chunks },
        { label: t("summary.facts.compression_configured"), value: yesNo(details.compression_enabled) },
      ]
    case "continuous_aggregate":
      return [
        { label: t("summary.facts.source_schema"), value: details.hypertable_schema },
        { label: t("summary.facts.source_hypertable"), value: details.hypertable_name },
        { label: t("summary.facts.materialization_schema"), value: details.materialization_hypertable_schema },
        { label: t("summary.facts.materialization_hypertable"), value: details.materialization_hypertable_name },
        { label: t("summary.facts.materialized_only"), value: yesNo(details.materialized_only) },
        { label: t("summary.facts.compression_configured"), value: yesNo(details.compression_enabled) },
      ]
    case "unavailable":
      return [{ label: t("summary.facts.timescale_metadata"), value: details.reason }]
    default:
      return unknownContents(details)
  }
}
