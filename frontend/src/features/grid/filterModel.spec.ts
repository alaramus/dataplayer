import { describe, expect, it } from "vitest"

import type { FetchColumn } from "@/client"

import {
  describeFilter,
  draftFor,
  operatorOptions,
  toFilter,
  validateDraft,
} from "./filterModel"

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

describe("what an applied filter reads as", () => {
  it("says the value, which is what explains an empty page", () => {
    expect(describeFilter({ column: "name", op: "eq", value: "PostgreSQL" })).toBe(
      'name equals "PostgreSQL"'
    )
  })

  it("shows an empty value as one rather than as nothing", () => {
    expect(describeFilter({ column: "name", op: "eq", value: "" })).toBe('name equals ""')
  })

  it("says no value for a null check, because there is none", () => {
    expect(describeFilter({ column: "name", op: "is_null" })).toBe("name is null")
  })

  it("lists a few of a set and counts the rest", () => {
    expect(
      describeFilter({ column: "id", op: "in", values: ["1", "2", "3", "4", "5"] })
    ).toBe('id is one of "1", "2", "3" +2 more')
  })

  it("cuts a value that would not fit on the line", () => {
    const long = "x".repeat(60)

    const said = describeFilter({ column: "note", op: "eq", value: long })

    expect(said).toBe(`note equals "${"x".repeat(40)}\u2026"`)
    expect(said.length).toBeLessThan(long.length + 20)
  })
})
