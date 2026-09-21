import { describe, expect, it } from "vitest"

import type { ColumnType } from "@/client"

import { inputHint } from "./model"

function typeOf(category: ColumnType["category"], sql: string = category, enum_values?: string[]): ColumnType {
  return { sql, category, ...(enum_values === undefined ? {} : { enum_values }) }
}

describe("what a cell of a type takes", () => {
  it("names the kind of value each category accepts", () => {
    expect(inputHint(typeOf("number", "numeric"))).toBe("a number")
    expect(inputHint(typeOf("boolean", "bool"))).toBe("true or false")
    expect(inputHint(typeOf("string", "text"))).toBe("any text")
    expect(inputHint(typeOf("uuid", "uuid"))).toBe("a UUID")
    expect(inputHint(typeOf("json", "jsonb"))).toBe("JSON")
  })

  it("lists the values an enum takes", () => {
    expect(inputHint(typeOf("enum", "project_status", ["active", "paused"]))).toBe(
      "one of: active, paused"
    )
  })

  it("covers every category", () => {
    const categories: ColumnType["category"][] = [
      "number",
      "boolean",
      "datetime",
      "enum",
      "json",
      "array",
      "uuid",
      "binary",
      "network",
      "string",
      "geometric",
      "range",
      "composite",
      "other",
    ]
    for (const category of categories) {
      expect(inputHint(typeOf(category)).length).toBeGreaterThan(0)
    }
  })
})
