import { describe, expect, it } from "vitest"

import type { DesignTypeOption } from "@/client"

import {
  dependents,
  emptyDraft,
  newCheck,
  newColumn,
  newForeignKey,
  newIndex,
  newTerm,
  predicateExpression,
  tally,
  toDefinition,
  withoutColumn,
  worthPlanning,
} from "./draft"
import type { Draft } from "./draft"

const types: DesignTypeOption[] = [
  { code: "text", title: "Text", sql: "text", parameters: [] },
  { code: "varchar", title: "Text, limited", sql: "varchar(n)", parameters: ["length"] },
  {
    code: "numeric",
    title: "Numeric",
    sql: "numeric(p,s)",
    parameters: ["precision", "scale"],
  },
]

function draftWith(name = "orders"): Draft {
  const draft = emptyDraft("text")
  draft.name = name
  return draft
}

describe("what crosses to the server", () => {
  it("sends the parameters the chosen type takes and no others", () => {
    const draft = draftWith()
    const column = draft.columns[0]!
    column.typeCode = "varchar"
    column.length = 40
    // Left over from a type chosen a moment ago: the server never sees it,
    // because a length on a type that takes none is a request about a type
    // that does not exist.
    column.precision = 12

    const definition = toDefinition(draft, types)

    expect(definition.columns[0]!.type).toEqual({
      code: "varchar",
      length: 40,
      precision: null,
      scale: null,
      dimensions: 0,
    })
  })

  it("keeps the primary key in the order it was built", () => {
    const draft = draftWith()
    const second = newColumn("text", 1)
    draft.columns.push(second)
    draft.primaryKey = [second.id, draft.columns[0]!.id]

    expect(toDefinition(draft, types).primary_key).toEqual({
      name: "",
      column_ids: [second.id, draft.columns[0]!.id],
    })
  })

  it("leaves out an index whose key names nothing yet", () => {
    const draft = draftWith()
    const index = newIndex("btree", "")
    draft.indexes.push(index)

    expect(toDefinition(draft, types).indexes).toEqual([])
  })

  it("leaves out a foreign key that points at nothing yet", () => {
    const draft = draftWith()
    draft.foreignKeys.push(newForeignKey("demo"))

    expect(toDefinition(draft, types).foreign_keys).toEqual([])
  })

  it("leaves out a check nobody has finished", () => {
    const draft = draftWith()
    const check = newCheck()
    check.predicate.terms.push(newTerm(draft.columns[0]!.id))
    draft.checks.push(check)

    expect(toDefinition(draft, types).checks).toEqual([])
  })
})

describe("conditions", () => {
  it("is the comparison itself when there is only one of them", () => {
    const term = newTerm("c1")
    term.operator = "gte"
    term.valueKind = "number"
    term.value = "0"

    expect(predicateExpression({ operator: "and", terms: [term] })).toEqual({
      kind: "compare",
      operator: "gte",
      left: { kind: "column", column_id: "c1" },
      right: { kind: "literal", value_kind: "number", text: "0" },
    })
  })

  it("groups several of them under the join that was chosen", () => {
    const one = newTerm("c1")
    one.value = "paid"
    const two = newTerm("c2")
    two.operator = "is_not_null"

    const expression = predicateExpression({ operator: "or", terms: [one, two] })

    expect(expression).toMatchObject({ kind: "group", operator: "or" })
  })

  it("drops the values of a membership that are still empty", () => {
    const term = newTerm("c1")
    term.operator = "in"
    term.values = ["new", "", "paid"]

    expect(predicateExpression({ operator: "and", terms: [term] })).toMatchObject({
      kind: "in",
      values: [
        { kind: "literal", value_kind: "text", text: "new" },
        { kind: "literal", value_kind: "text", text: "paid" },
      ],
    })
  })

  it("is nothing at all while no term is finished", () => {
    expect(predicateExpression({ operator: "and", terms: [newTerm("c1")] })).toBeNull()
  })
})

describe("removing a column", () => {
  it("names everything that would go with it", () => {
    const draft = draftWith()
    const column = draft.columns[0]!
    const index = newIndex("btree", column.id)
    index.name = "orders_id_idx"
    draft.indexes.push(index)

    expect(dependents(draft, column.id)).toEqual(["the primary key", "orders_id_idx"])
  })

  it("takes every reference to it out, and drops what is left empty", () => {
    const draft = draftWith()
    const column = draft.columns[0]!
    const other = newColumn("text", 1)
    draft.columns.push(other)
    draft.indexes.push(newIndex("btree", column.id))

    const left = withoutColumn(draft, column.id)

    expect(left.columns.map((one) => one.id)).toEqual([other.id])
    expect(left.primaryKey).toEqual([])
    // An index with no keys left is not an index.
    expect(left.indexes).toEqual([])
  })
})

describe("what the editor says about itself", () => {
  it("waits for a name and for every column to have one", () => {
    const draft = emptyDraft("text")
    expect(worthPlanning(draft)).toBe(false)

    draft.name = "orders"
    expect(worthPlanning(draft)).toBe(true)

    draft.columns[0]!.name = ""
    expect(worthPlanning(draft)).toBe(false)
  })

  it("counts what is there and leaves out what is not", () => {
    const draft = draftWith()

    expect(tally(draft)).toBe("1 column")

    draft.indexes.push(newIndex("btree", draft.columns[0]!.id))
    expect(tally(draft)).toBe("1 column · 1 index")
  })
})
