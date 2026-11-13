import { describe, expect, it } from "vitest"

import { fieldName, holdsHash, keyedProblem } from "./keyed"

describe("a link keeping the latest per key (D314)", () => {
  it("names a field by itself, and leaves other columns as they are", () => {
    expect(fieldName("value.price")).toBe("price")
    expect(fieldName("value.")).toBe("value.")
    expect(fieldName("price")).toBe("price")
  })

  it("says what is missing before it can be kept", () => {
    const byKey = { key_column: "key", prefix: "price:", ttl_seconds: null }
    expect(keyedProblem({ byKey: { ...byKey, key_column: "" }, columns: [{ source: "value", target: "value" }] })).toBe("key")
    expect(keyedProblem({ byKey, columns: [] })).toBe("values")
    const twice = [{ source: "a", target: "x" }, { source: "b", target: "x" }]
    expect(keyedProblem({ byKey, columns: twice })).toBe("names")
    expect(keyedProblem({ byKey, columns: [{ source: "value", target: "" }] })).toBeNull()
  })

  it("holds a hash only for several values", () => {
    expect(holdsHash([{ source: "a", target: "a" }])).toBe(false)
    expect(holdsHash([{ source: "a", target: "a" }, { source: "b", target: "b" }])).toBe(true)
  })
})
