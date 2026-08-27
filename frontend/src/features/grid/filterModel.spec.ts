import { describe, expect, it } from "vitest"

import type { FetchColumn } from "@/client"

import { draftFor, operatorOptions, toFilter, validateDraft } from "./filterModel"

const NUMBER_COLUMN: FetchColumn = {
  name: "amount",
  type: { sql: "numeric", category: "number" },
  sortable: true,
  filter_operators: ["eq", "gt", "in", "is_null"],
}

describe("filter drafts", () => {
  it("starts with the first operator in the order supplied by the server", () => {
    expect(draftFor(NUMBER_COLUMN)).toEqual({
      column: "amount",
      op: "eq",
      value: "",
      values: [],
    })
  })

  it("omits a value for a null check", () => {
    expect(
      toFilter({ column: "deleted_at", op: "is_null", value: "ignored", values: [] })
    ).toEqual({ column: "deleted_at", op: "is_null" })
  })

  it("requires one item for in", () => {
    expect(validateDraft({ column: "status", op: "in", value: "", values: [] })).toBe(
      "Add at least one value"
    )
  })

  it("requires text for a scalar operator", () => {
    expect(validateDraft({ column: "amount", op: "gt", value: "", values: [] })).toBe(
      "Enter a value"
    )
  })

  it("never offers an operator absent from the server column", () => {
    expect(operatorOptions(NUMBER_COLUMN)).not.toContain("contains")
  })
})
