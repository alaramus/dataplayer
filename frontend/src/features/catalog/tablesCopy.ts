/**
 * A copy of tables with their structure, as plain decisions (D182).
 *
 * The server plans the copy at every change of a choice; these functions only
 * turn what the window holds into a choice and what the server answers into
 * what the window shows.
 */

import type { CopiedRow, TablesChoice, TablesPreview } from "@/client"

export type RowsChoice = "rows" | "structure"
export type LinksChoice = "copy" | "drop" | "keep"

/** What the window holds, before it is a request. */
export interface CopyChoices {
  /** New names typed, by the table's node id at the source. */
  names: Record<string, string>
  rows: RowsChoice
  /** Null until chosen: the server keeps links within one database and copies them otherwise. */
  links: LinksChoice | null
  also: string[]
}

export function choiceOf(choices: CopyChoices): TablesChoice {
  return {
    names: { ...choices.names },
    rows: choices.rows === "rows",
    links: choices.links,
    also: [...choices.also],
  }
}

/**
 * The choice Copy runs with: every table named as the window shows it, so the
 * job makes what was reviewed rather than asking for free names again.
 */
export function runChoice(choices: CopyChoices, preview: TablesPreview): TablesChoice {
  return {
    ...choiceOf(choices),
    names: Object.fromEntries(
      preview.tables.map((table) => [table.node_id, choices.names[table.node_id] ?? table.name])
    ),
    links: choices.links ?? preview.links,
  }
}

/**
 * The schema the window starts in: where the catalog stood when it was one,
 * then public, then the first. The person chooses from there.
 */
export function startingPlace(
  places: { label: string; value: string }[],
  standing: string | null
): string | null {
  if (standing !== null && places.some((place) => place.value === standing)) return standing
  return (places.find((place) => place.label === "public") ?? places[0])?.value ?? null
}

/** Why a table is in the copy when nobody ticked it. */
export function originNote(row: CopiedRow): string | undefined {
  if (row.origin === "linked") return "a copied table points at it"
  if (row.origin === "added") return "it points at a copied table"
  return undefined
}

/** Every step of the copy in the order it runs, as one script to read. */
export function copyScript(preview: TablesPreview): string {
  const before = preview.statements.filter((statement) => statement.stage !== "after")
  const after = preview.statements.filter((statement) => statement.stage === "after")
  const lines = [
    ...before.map((statement) => `-- ${statement.title}\n${statement.sql};`),
    ...preview.loads.map(
      (load) => `-- The rows of ${load.node_id} arrive in ${load.schema_name}.${load.name}`
    ),
    ...after.map((statement) => `-- ${statement.title}\n${statement.sql};`),
  ]
  return lines.join("\n\n")
}

/** What will not come across, a line per table that leaves anything behind. */
export function leftBehind(preview: TablesPreview): string[] {
  return preview.tables
    .filter((table) => table.left_behind.length > 0)
    .map((table) => `${table.label}: ${table.left_behind.join(", ")}`)
}
