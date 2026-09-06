import { describe, expect, it } from "vitest"

import { emptyDraft, newTerm } from "./draft"
import { predicateLabel } from "./predicateLabel"

describe("predicate field label", () => {
  it("follows a renamed column and keeps the typed condition intact", () => {
    const draft = emptyDraft("text")
    const column = draft.columns[0]!
    const term = newTerm(column.id)
    term.value = "paid"
    const predicate = { operator: "and" as const, terms: [term] }
    column.name = "status"
    expect(predicateLabel(predicate, draft.columns)).toBe("status = 'paid'")
    column.name = "state"
    expect(predicateLabel(predicate, draft.columns)).toBe("state = 'paid'")
    expect(term.columnId).toBe(column.id)
  })

  it("labels lists and null tests without losing punctuation inside a value", () => {
    const draft = emptyDraft("text")
    const term = newTerm(draft.columns[0]!.id)
    term.operator = "in"
    term.values = ["a,b", "it's paid"]
    const predicate = { operator: "or" as const, terms: [term] }
    expect(predicateLabel(predicate, draft.columns)).toBe("id IN ('a,b', 'it''s paid')")
    term.operator = "is_not_null"
    expect(predicateLabel(predicate, draft.columns)).toBe("id IS NOT NULL")
  })
})
