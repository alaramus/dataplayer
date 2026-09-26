/**
 * The window that declares a table over a folder, as plain decisions (D170).
 *
 * The server proposes the fields of the folder's first hashes and says which
 * names a column may not take; these functions only keep what the person
 * ticks, types and adds, and say why Save is off.
 */

import type { DeclareTableRequest, ProposedColumn, TableProposal } from "@/client"
import type { SelectOption } from "@/shared/ui"

export type DeclaredType = ProposedColumn["type"]

/** What the server keeps at most; the window says so before Save does. */
export const MAX_COLUMNS = 200

export const TYPE_OPTIONS: SelectOption[] = [
  { label: "Text", value: "text" },
  { label: "Number", value: "number" },
  { label: "Boolean", value: "boolean" },
  { label: "Date and time", value: "datetime" },
]

export interface FieldDraft {
  name: string
  type: DeclaredType
  ticked: boolean
  /** How many sampled hashes hold it; null for a field added by hand. */
  foundIn: number | null
}

export interface TableDraft {
  name: string
  fields: FieldDraft[]
  sampled: number
  declared: boolean
  reserved: string[]
}

export function draftOf(proposal: TableProposal): TableDraft {
  return {
    name: proposal.name,
    fields: proposal.columns.map((column) => ({
      name: column.name,
      type: column.type,
      ticked: column.ticked,
      foundIn: column.found_in,
    })),
    sampled: proposal.sampled,
    declared: proposal.declared,
    reserved: proposal.reserved ?? [],
  }
}

/** The draft with a field typed by hand at the end, ticked, or why not. */
export function withField(draft: TableDraft, typed: string): TableDraft | string {
  const name = typed.trim()
  if (name === "") return "Type the name of a field"
  if (draft.reserved.includes(name)) return `${name} is the table's first column`
  if (draft.fields.some((field) => field.name === name)) return `${name} is already listed`
  return {
    ...draft,
    fields: [...draft.fields, { name, type: "text", ticked: true, foundIn: null }],
  }
}

/** Why the draft cannot be saved yet, or nothing when it can. */
export function draftProblem(draft: TableDraft): string | null {
  if (draft.name.trim() === "") return "Name the table"
  const ticked = draft.fields.filter((field) => field.ticked).length
  if (ticked === 0) return "Tick at least one field"
  if (ticked > MAX_COLUMNS) return `A table holds at most ${String(MAX_COLUMNS)} columns`
  return null
}

/** What Save sends: the ticked fields, in the order they are listed. */
export function declarationOf(nodeId: string, draft: TableDraft): DeclareTableRequest {
  return {
    node_id: nodeId,
    name: draft.name.trim(),
    columns: draft.fields
      .filter((field) => field.ticked)
      .map((field) => ({ name: field.name, type: field.type })),
  }
}

/** Where the sample met a field: "2 of 3", or that it was added. */
export function foundText(field: FieldDraft, sampled: number): string {
  if (field.foundIn === null) return "Added"
  return `${String(field.foundIn)} of ${String(sampled)}`
}
