import type { connectorsReadRelationModelResponses } from "@/client"

export type RelationModel = connectorsReadRelationModelResponses[200]
export type Constraint = NonNullable<RelationModel["constraints"]>[number]
export type ForeignKey = Extract<Constraint, { kind: "foreign_key" }>
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
