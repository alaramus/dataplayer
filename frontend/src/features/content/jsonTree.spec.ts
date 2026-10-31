import { describe, expect, it } from "vitest"

import { childrenOf, closedSummary, documentId, scalarOf, typedScalar } from "./jsonTree"
import type { JsonValue } from "./jsonTree"

const text = (value: string): JsonValue => ({ kind: "string", value })
const number = (value: string): JsonValue => ({ kind: "number", value })
const object = (entries: Record<string, JsonValue>): JsonValue => ({
  kind: "object",
  entries: Object.entries(entries).map(([name, value]) => ({ name, value })),
})

describe("a value of a JSON tree", () => {
  it("draws a one-field $ object as the BSON value it stands for", () => {
    expect(typedScalar(object({ $oid: text("65aa") }))).toEqual({ type: "ObjectId", text: "65aa", tone: "typed" })
    expect(typedScalar(object({ $date: text("2026-01-02T00:00:00Z") }))?.type).toBe("Date")
    expect(typedScalar(object({ $date: object({ $numberLong: text("253402300800000") }) }))?.text).toBe(
      "253402300800000"
    )
    expect(typedScalar(object({ $numberDecimal: text("1.10") }))?.text).toBe("1.10")
    expect(typedScalar(object({ $binary: object({ base64: text("eA=="), subType: text("05") }) }))).toEqual({
      type: "Binary(05)",
      text: "eA==",
      tone: "typed",
    })
    expect(typedScalar(object({ $regularExpression: object({ pattern: text("^a"), options: text("i") }) }))?.text)
      .toBe("/^a/i")
  })

  it("leaves an ordinary object to be opened", () => {
    expect(typedScalar(object({ city: text("Riga") }))).toBeNull()
    expect(typedScalar(object({ $oid: text("1"), other: text("2") }))).toBeNull()
    expect(scalarOf(object({ city: text("Riga") }))).toBeNull()
  })

  it("reads JSON's own scalars, a string in its quotes", () => {
    expect(scalarOf(text("Ann"))?.text).toBe('"Ann"')
    expect(scalarOf(number("9007199254740993"))?.text).toBe("9007199254740993")
    expect(scalarOf({ kind: "null", value: null })?.tone).toBe("word")
  })

  it("draws an empty object or array as itself, with nothing to open", () => {
    expect(scalarOf(object({}))?.text).toBe("{ }")
    expect(scalarOf({ kind: "array", items: [] })?.text).toBe("[ ]")
  })

  it("names an array's children by position and says how much is closed inside", () => {
    const array: JsonValue = { kind: "array", items: [text("a"), text("b")] }

    expect(childrenOf(array).map((child) => child.name)).toEqual(["0", "1"])
    expect(closedSummary(array)).toBe("[ 2 ]")
    expect(closedSummary(object({ a: text("x") }))).toBe("{ 1 }")
  })

  it("names a document by its _id", () => {
    expect(documentId(object({ _id: object({ $oid: text("65aa") }), name: text("Ann") }))).toBe("65aa")
    expect(documentId(object({ _id: number("7") }))).toBe("7")
    expect(documentId(object({ name: text("no id") }))).toBe("")
  })
})
