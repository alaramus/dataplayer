import type {
  DesignCheck,
  DesignForeignKey,
  DesignIndex,
  DesignTypeOption,
  TableDefinition,
} from "@/client"

/**
 * One node of the expression model, named after where it is used.
 *
 * The generated client inlines the union rather than exporting it, so it is
 * taken from the field that carries it; naming it here keeps every builder
 * below reading as what it builds.
 */
type Expression = DesignCheck["expression"]

/**
 * The table being designed, as the editor holds it.
 *
 * Not the request shape. A form holds half-finished things — an index with no
 * key yet, a length being typed — and the definition that crosses to the
 * server holds none of them; `toDefinition` is the one place that turns one
 * into the other. Keeping the two apart is what lets the editor stay usable
 * while the draft is incomplete, instead of the request model deciding what a
 * person is allowed to type next.
 *
 * Every object carries an id the browser made up. Keys, indexes and
 * expressions refer to columns by that id and never by name, so renaming or
 * reordering a column changes nothing else (D117).
 */

export type DraftSection =
  | "columns"
  | "indexes"
  | "foreign-keys"
  | "constraints"
  | "options"

export type CompareOperator =
  | "eq"
  | "ne"
  | "lt"
  | "lte"
  | "gt"
  | "gte"
  | "in"
  | "not_in"
  | "is_null"
  | "is_not_null"

export type LiteralKind = "text" | "number" | "boolean" | "json"

export interface DraftTerm {
  id: string
  columnId: string
  operator: CompareOperator
  valueKind: LiteralKind
  value: string
  /** For membership, which takes a bounded list rather than one value. */
  values: string[]
}

export interface DraftPredicate {
  operator: "and" | "or"
  terms: DraftTerm[]
}

export type DraftGeneration =
  | { kind: "none" }
  | { kind: "literal"; value: string }
  | { kind: "expression"; function: string }
  | {
      kind: "identity"
      generated: "always" | "by_default"
      start: number | null
      increment: number | null
    }
  | { kind: "generated"; function: string; columnId: string }

export interface DraftColumn {
  id: string
  name: string
  typeCode: string
  length: number | null
  precision: number | null
  scale: number | null
  dimensions: number
  notNull: boolean
  comment: string
  collation: string
  generation: DraftGeneration
}

export interface DraftIndexKey {
  id: string
  kind: "column" | "expression"
  columnId: string
  /** The published function code, when the key is an expression over a column. */
  function: string
  direction: "" | "asc" | "desc"
  nulls: "" | "first" | "last"
  operatorClass: string
}

export interface DraftIndex {
  id: string
  name: string
  method: string
  unique: boolean
  keys: DraftIndexKey[]
  includeColumnIds: string[]
  predicate: DraftPredicate
}

export interface DraftForeignKey {
  id: string
  name: string
  columnIds: string[]
  /** Where the picker is looking, kept because a node id is never taken apart. */
  targetSchemaId: string
  targetNodeId: string
  targetLabel: string
  targetColumns: string[]
  onUpdate: string
  onDelete: string
  match: "simple" | "full"
  deferrable: boolean
  initiallyDeferred: boolean
}

export interface DraftUnique {
  id: string
  name: string
  columnIds: string[]
  nullsNotDistinct: boolean
  deferrable: boolean
  initiallyDeferred: boolean
}

export interface DraftCheck {
  id: string
  name: string
  predicate: DraftPredicate
}

export interface Draft {
  name: string
  comment: string
  persistence: "permanent" | "unlogged"
  columns: DraftColumn[]
  /** In key order, which is not the order the columns are declared in. */
  primaryKey: string[]
  uniques: DraftUnique[]
  checks: DraftCheck[]
  foreignKeys: DraftForeignKey[]
  indexes: DraftIndex[]
  partitionStrategy: "" | "range" | "list" | "hash"
  partitionColumnIds: string[]
}

let counter = 0

/** A draft id: short, unique within this window, and never sent as a name. */
export function newId(prefix: string): string {
  counter += 1
  return `${prefix}${String(counter)}`
}

export function newColumn(typeCode: string, at: number): DraftColumn {
  return {
    id: newId("c"),
    name: at === 0 ? "id" : `column_${String(at + 1)}`,
    typeCode,
    length: null,
    precision: null,
    scale: null,
    dimensions: 0,
    notNull: at === 0,
    comment: "",
    collation: "",
    generation: { kind: "none" },
  }
}

export function newPredicate(): DraftPredicate {
  return { operator: "and", terms: [] }
}

export function newTerm(columnId: string): DraftTerm {
  return {
    id: newId("t"),
    columnId,
    operator: "eq",
    valueKind: "text",
    value: "",
    values: [""],
  }
}

export function newIndexKey(columnId: string): DraftIndexKey {
  return {
    id: newId("k"),
    kind: "column",
    columnId,
    function: "",
    direction: "",
    nulls: "",
    operatorClass: "",
  }
}

export function emptyDraft(typeCode: string): Draft {
  const first = newColumn(typeCode, 0)
  return {
    name: "",
    comment: "",
    persistence: "permanent",
    columns: [first],
    primaryKey: [first.id],
    uniques: [],
    checks: [],
    foreignKeys: [],
    indexes: [],
    partitionStrategy: "",
    partitionColumnIds: [],
  }
}

/** Every place a column is referred to, so removing one can say what it costs. */
export function dependents(draft: Draft, columnId: string): string[] {
  const named: string[] = []
  if (draft.primaryKey.includes(columnId)) named.push("the primary key")
  for (const unique of draft.uniques) {
    if (unique.columnIds.includes(columnId)) named.push(unique.name || "a unique constraint")
  }
  for (const foreign of draft.foreignKeys) {
    if (foreign.columnIds.includes(columnId)) named.push(foreign.name || "a foreign key")
  }
  for (const index of draft.indexes) {
    const inKeys = index.keys.some((key) => key.columnId === columnId)
    const carried = index.includeColumnIds.includes(columnId)
    const filtered = index.predicate.terms.some((term) => term.columnId === columnId)
    if (inKeys || carried || filtered) named.push(index.name || "an index")
  }
  for (const check of draft.checks) {
    if (check.predicate.terms.some((term) => term.columnId === columnId)) {
      named.push(check.name || "a check")
    }
  }
  for (const column of draft.columns) {
    if (column.generation.kind === "generated" && column.generation.columnId === columnId) {
      named.push(column.name)
    }
  }
  return named
}

/**
 * The same column list, with one column gone and every reference to it too.
 *
 * Called only after the reader has been told what it takes with it: the point
 * of `dependents` is that the answer arrives before the deletion rather than
 * after, instead of dependent definitions quietly disappearing with the
 * column.
 */
export function withoutColumn(draft: Draft, columnId: string): Draft {
  return {
    ...draft,
    columns: draft.columns
      .filter((column) => column.id !== columnId)
      .map((column) =>
        column.generation.kind === "generated" && column.generation.columnId === columnId
          ? { ...column, generation: { kind: "none" } as DraftGeneration }
          : column
      ),
    primaryKey: draft.primaryKey.filter((id) => id !== columnId),
    uniques: draft.uniques
      .map((unique) => ({
        ...unique,
        columnIds: unique.columnIds.filter((id) => id !== columnId),
      }))
      .filter((unique) => unique.columnIds.length > 0),
    foreignKeys: draft.foreignKeys
      .map((foreign) => ({
        ...foreign,
        columnIds: foreign.columnIds.filter((id) => id !== columnId),
      }))
      .filter((foreign) => foreign.columnIds.length > 0),
    indexes: draft.indexes
      .map((index) => ({
        ...index,
        keys: index.keys.filter((key) => key.columnId !== columnId),
        includeColumnIds: index.includeColumnIds.filter((id) => id !== columnId),
        predicate: {
          ...index.predicate,
          terms: index.predicate.terms.filter((term) => term.columnId !== columnId),
        },
      }))
      .filter((index) => index.keys.length > 0),
    checks: draft.checks.map((check) => ({
      ...check,
      predicate: {
        ...check.predicate,
        terms: check.predicate.terms.filter((term) => term.columnId !== columnId),
      },
    })),
    partitionColumnIds: draft.partitionColumnIds.filter((id) => id !== columnId),
  }
}

/** What a term becomes, or nothing while it is still being filled in. */
export function termExpression(term: DraftTerm): Expression | null {
  if (term.columnId === "") return null
  const column: Expression = { kind: "column", column_id: term.columnId }
  if (term.operator === "is_null" || term.operator === "is_not_null") {
    return {
      kind: "null_test",
      operand: column,
      negated: term.operator === "is_not_null",
    }
  }
  if (term.operator === "in" || term.operator === "not_in") {
    const values = term.values.filter((value) => value.trim() !== "")
    if (values.length === 0) return null
    return {
      kind: "in",
      operand: column,
      negated: term.operator === "not_in",
      values: values.map((value) => ({
        kind: "literal",
        value_kind: term.valueKind,
        text: value,
      })),
    }
  }
  if (term.value.trim() === "") return null
  return {
    kind: "compare",
    operator: term.operator,
    left: column,
    right: { kind: "literal", value_kind: term.valueKind, text: term.value },
  }
}

/**
 * A whole predicate, or nothing when no term of it is finished.
 *
 * One term stands on its own rather than becoming a group of one: the server
 * would compose the same thing either way, and the SQL a person reads back
 * should look like what they wrote.
 */
export function predicateExpression(predicate: DraftPredicate): Expression | null {
  const terms = predicate.terms
    .map(termExpression)
    .filter((term): term is Expression => term !== null)
  if (terms.length === 0) return null
  const [only] = terms
  if (terms.length === 1 && only !== undefined) return only
  return { kind: "group", operator: predicate.operator, terms }
}

function generation(column: DraftColumn): DesignColumn["generation"] {
  const chosen = column.generation
  switch (chosen.kind) {
    case "literal":
      return { kind: "literal", value: chosen.value }
    case "expression":
      return chosen.function === ""
        ? { kind: "none" }
        : {
            kind: "expression",
            expression: { kind: "call", function: chosen.function, arguments: [] },
          }
    case "identity":
      return {
        kind: "identity",
        generated: chosen.generated,
        start: chosen.start,
        increment: chosen.increment,
      }
    case "generated":
      return chosen.function === "" || chosen.columnId === ""
        ? { kind: "none" }
        : {
            kind: "generated",
            expression: {
              kind: "call",
              function: chosen.function,
              arguments: [{ kind: "column", column_id: chosen.columnId }],
            },
          }
    default:
      return { kind: "none" }
  }
}

type DesignColumn = TableDefinition["columns"][number]

function columnType(column: DraftColumn, types: DesignTypeOption[]): DesignColumn["type"] {
  const known = types.find((option) => option.code === column.typeCode)
  const takes = known?.parameters ?? []
  return {
    code: column.typeCode,
    length: takes.includes("length") ? column.length : null,
    precision: takes.includes("precision") ? column.precision : null,
    scale: takes.includes("scale") ? column.scale : null,
    dimensions: column.dimensions,
  }
}

function index(draft: DraftIndex): DesignIndex {
  return {
    id: draft.id,
    name: draft.name,
    method: draft.method,
    unique: draft.unique,
    keys: draft.keys.map((key) =>
      key.kind === "expression" && key.function !== ""
        ? {
            kind: "expression",
            expression: {
              kind: "call",
              function: key.function,
              arguments: [{ kind: "column", column_id: key.columnId }],
            },
            direction: key.direction === "" ? null : key.direction,
            nulls: key.nulls === "" ? null : key.nulls,
            operator_class: key.operatorClass === "" ? null : key.operatorClass,
          }
        : {
            kind: "column",
            column_id: key.columnId,
            direction: key.direction === "" ? null : key.direction,
            nulls: key.nulls === "" ? null : key.nulls,
            operator_class: key.operatorClass === "" ? null : key.operatorClass,
          }
    ),
    include_column_ids: draft.includeColumnIds,
    predicate: predicateExpression(draft.predicate),
  }
}

function foreignKey(draft: DraftForeignKey): DesignForeignKey {
  return {
    id: draft.id,
    name: draft.name,
    column_ids: draft.columnIds,
    target_node_id: draft.targetNodeId,
    target_columns: draft.targetColumns,
    on_update: draft.onUpdate as DesignForeignKey["on_update"],
    on_delete: draft.onDelete as DesignForeignKey["on_delete"],
    match: draft.match,
    deferrable: draft.deferrable,
    initially_deferred: draft.initiallyDeferred,
  }
}

/**
 * The request the server is asked to plan, out of what the form holds.
 *
 * Half-finished objects are left out rather than sent as something else: an
 * index with no key yet is not an index the server should have an opinion
 * about, and a foreign key pointing at nothing is not a refusal worth showing
 * while it is still being filled in.
 */
export function toDefinition(draft: Draft, types: DesignTypeOption[]): TableDefinition {
  return {
    name: draft.name,
    comment: draft.comment === "" ? null : draft.comment,
    persistence: draft.persistence,
    columns: draft.columns.map((column) => ({
      id: column.id,
      name: column.name,
      type: columnType(column, types),
      not_null: column.notNull,
      comment: column.comment === "" ? null : column.comment,
      collation: column.collation === "" ? null : column.collation,
      generation: generation(column),
    })),
    primary_key:
      draft.primaryKey.length === 0 ? null : { name: "", column_ids: draft.primaryKey },
    unique_constraints: draft.uniques
      .filter((unique) => unique.columnIds.length > 0)
      .map((unique) => ({
        id: unique.id,
        name: unique.name,
        column_ids: unique.columnIds,
        nulls_not_distinct: unique.nullsNotDistinct,
        deferrable: unique.deferrable,
        initially_deferred: unique.initiallyDeferred,
      })),
    checks: draft.checks.flatMap((check) => {
      const expression = predicateExpression(check.predicate)
      return expression === null
        ? []
        : [{ id: check.id, name: check.name, expression }]
    }),
    foreign_keys: draft.foreignKeys
      .filter(
        (foreign) =>
          foreign.targetNodeId !== "" &&
          foreign.columnIds.length > 0 &&
          foreign.targetColumns.length > 0
      )
      .map(foreignKey),
    indexes: draft.indexes
      .filter((draftIndex) =>
        draftIndex.keys.every(
          (key) =>
            key.columnId !== "" && (key.kind === "column" || key.function !== "")
        )
      )
      .map(index),
    partition:
      draft.partitionStrategy === "" || draft.partitionColumnIds.length === 0
        ? null
        : {
            strategy: draft.partitionStrategy,
            column_ids: draft.partitionColumnIds,
          },
  }
}

/** Whether there is enough of a table here to ask the server about it. */
export function worthPlanning(draft: Draft): boolean {
  return (
    draft.name.trim() !== "" &&
    draft.columns.length > 0 &&
    draft.columns.every((column) => column.name.trim() !== "")
  )
}

/** The one line under the editor: what this draft holds. */
export function tally(draft: Draft): string {
  const parts = [
    `${String(draft.columns.length)} ${draft.columns.length === 1 ? "column" : "columns"}`,
  ]
  if (draft.indexes.length > 0) {
    parts.push(
      `${String(draft.indexes.length)} ${draft.indexes.length === 1 ? "index" : "indexes"}`
    )
  }
  const constraints =
    draft.uniques.length + draft.checks.length + draft.foreignKeys.length
  if (constraints > 0) {
    parts.push(
      `${String(constraints)} ${constraints === 1 ? "constraint" : "constraints"}`
    )
  }
  return parts.join(" · ")
}

export function newIndex(method: string, columnId: string): DraftIndex {
  return {
    id: newId("i"),
    name: "",
    method,
    unique: false,
    keys: [newIndexKey(columnId)],
    includeColumnIds: [],
    predicate: newPredicate(),
  }
}

export function newForeignKey(schemaId: string): DraftForeignKey {
  return {
    id: newId("f"),
    name: "",
    columnIds: [],
    targetSchemaId: schemaId,
    targetNodeId: "",
    targetLabel: "",
    targetColumns: [],
    onUpdate: "no_action",
    onDelete: "no_action",
    match: "simple",
    deferrable: false,
    initiallyDeferred: false,
  }
}

export function newUnique(columnId: string): DraftUnique {
  return {
    id: newId("u"),
    name: "",
    columnIds: columnId === "" ? [] : [columnId],
    nullsNotDistinct: false,
    deferrable: false,
    initiallyDeferred: false,
  }
}

export function newCheck(): DraftCheck {
  return { id: newId("k"), name: "", predicate: newPredicate() }
}
