import type { connectorsReadRelationModelResponses } from "@/client"
import { formatSize } from "@/features/catalog/nodes"

export type RelationModel = connectorsReadRelationModelResponses[200]
export type Constraint = NonNullable<RelationModel["constraints"]>[number]
export type ForeignKey = Extract<Constraint, { kind: "foreign_key" }>
/**
 * What happens to a referencing row, in the source's own closed vocabulary.
 *
 * Read off the generated key rather than written out again: the two cannot
 * then drift apart, and the generator inlines the union instead of naming it.
 */
export type RefAction = NonNullable<ForeignKey["on_delete"]>
export type Column = NonNullable<RelationModel["columns"]>[number]

export interface ColumnBadge {
  kind: "primary_key" | "foreign_key" | "unique" | "index"
  label: string
  tooltip: string
}

export function badgesFor(model: RelationModel, columnName: string): ColumnBadge[] {
  const badges: ColumnBadge[] = []
  for (const constraint of model.constraints ?? []) {
    if (constraint.kind === "check" || constraint.kind === "exclude") continue
    if (!constraint.columns.includes(columnName)) continue
    if (constraint.kind === "primary_key") {
      badges.push({ kind: "primary_key", label: "PK", tooltip: constraint.name })
    } else if (constraint.kind === "foreign_key") {
      badges.push({ kind: "foreign_key", label: "FK", tooltip: foreignKeyLabel(constraint) })
    } else {
      badges.push({ kind: "unique", label: "U", tooltip: constraint.name })
    }
  }
  for (const index of model.indexes ?? []) {
    if (index.primary || index.unique) continue
    if ((index.columns ?? []).includes(columnName)) {
      badges.push({ kind: "index", label: "IX", tooltip: index.name })
    }
  }
  return badges
}

export function foreignKeyLabel(key: ForeignKey): string {
  return `${key.columns.join(", ")} → ${key.target_node_id} (${key.target_columns.join(", ")})`
}

/** What only this relation's own file format knows about it (D51). */
export type DatasetInfo = NonNullable<RelationModel["dataset"]>

export interface DatasetFact {
  label: string
  value: string
}

/**
 * The format's own facts, as lines to print.
 *
 * The switch is exhaustive: a format added to the union on the server is a
 * type error here until somebody decides what a reader should be told about
 * it. That is the whole reason the facts travel as a union rather than as
 * pairs of strings the source wrote.
 */
export function datasetFacts(dataset: DatasetInfo): DatasetFact[] {
  switch (dataset.kind) {
    case "parquet":
      return [
        { label: "Format", value: `Parquet ${dataset.format_version}` },
        { label: "Rows", value: String(dataset.rows) },
        { label: "Row groups", value: String(dataset.row_groups) },
        { label: "Columns", value: String(dataset.columns) },
        ...((dataset.compression ?? []).length === 0
          ? []
          : [{ label: "Compression", value: (dataset.compression ?? []).join(", ") }]),
        ...(dataset.created_by === null || dataset.created_by === undefined
          ? []
          : [{ label: "Written by", value: dataset.created_by }]),
        { label: "Size", value: formatSize(dataset.size_bytes) },
      ]
    case "worksheet":
      return [
        { label: "Format", value: "Worksheet" },
        { label: "Workbook", value: dataset.workbook },
        {
          label: "Sheet",
          value: `${dataset.sheet_name} (${String(dataset.sheet_position)} of ${String(dataset.sheet_count)})`,
        },
        ...(dataset.hidden === true ? [{ label: "Hidden", value: "yes" }] : []),
        ...(dataset.rows === null || dataset.rows === undefined
          ? []
          : [{ label: "Rows", value: String(dataset.rows) }]),
        ...(dataset.columns === null || dataset.columns === undefined
          ? []
          : [{ label: "Columns", value: String(dataset.columns) }]),
      ]
    default:
      return unknownFormat(dataset)
  }
}

function unknownFormat(dataset: never): never {
  throw new Error(`Unknown dataset format: ${JSON.stringify(dataset)}`)
}
