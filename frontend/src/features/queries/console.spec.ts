import { describe, expect, it } from "vitest"

import type { PreparedScript } from "@/client"

import {
  bindingsOf,
  elapsed,
  parameterForm,
  ready,
  statementAt,
  targetFor,
  toRemember,
  wholeDocument,
} from "./console"

/** `select 1;\nselect 2;\nselect 3` as the source describes it. */
const TEXT = "select 1;\nselect 2;\nselect 3"
const SCRIPT: PreparedScript = {
  statements: [
    { ordinal: 0, start: 0, end: 8, text: "select 1", kind: "read", changes: false, parameters: [], targets: [] },
    { ordinal: 1, start: 10, end: 18, text: "select 2", kind: "read", changes: false, parameters: [], targets: [] },
    { ordinal: 2, start: 20, end: 28, text: "select 3", kind: "read", changes: false, parameters: [], targets: [] },
  ],
  parameters: [],
}

const caret = (at: number) => ({ from: at, to: at })

describe("what Run means", () => {
  it("takes the statement the caret is inside", () => {
    expect(statementAt(SCRIPT, 3)?.ordinal).toBe(0)
    expect(statementAt(SCRIPT, 12)?.ordinal).toBe(1)
    expect(statementAt(SCRIPT, 25)?.ordinal).toBe(2)
  })

  it("gives a caret between two statements the one before it", () => {
    // Where somebody who has just finished typing leaves it.
    expect(statementAt(SCRIPT, 9)?.ordinal).toBe(0)
  })

  it("gives a caret before everything the first statement", () => {
    expect(statementAt(SCRIPT, 0)?.ordinal).toBe(0)
  })

  it("runs one statement and never the whole document", () => {
    const target = targetFor(SCRIPT, TEXT, caret(12))

    expect(target).toEqual({ text: "select 2", start: 10, end: 18, scope: "statement" })
  })

  it("runs a selection of one whole statement as that statement", () => {
    const target = targetFor(SCRIPT, TEXT, { from: 10, to: 18 })

    expect(target).toEqual({ text: "select 2", start: 10, end: 18, scope: "statement" })
  })

  it("runs a fragment selected inside one statement as the whole statement", () => {
    // Undo leaves the restored text selected; running the literal fragment
    // would only be refused as an unknown statement.
    const target = targetFor(SCRIPT, TEXT, { from: 12, to: 15 })

    expect(target).toEqual({ text: "select 2", start: 10, end: 18, scope: "statement" })
  })

  it("runs a selection spanning parts of two statements as a script, as it is", () => {
    const target = targetFor(SCRIPT, TEXT, { from: 4, to: 14 })

    expect(target).toEqual({ text: "ct 1;\nsele", start: 4, end: 14, scope: "script" })
  })

  it("calls a selection holding several statements a script", () => {
    const target = targetFor(SCRIPT, TEXT, { from: 0, to: 18 })

    expect(target?.scope).toBe("script")
    expect(target?.text).toBe("select 1;\nselect 2")
  })

  it("runs nothing for a selection of whitespace", () => {
    expect(targetFor(SCRIPT, TEXT, { from: 9, to: 10 })).toBeNull()
  })

  it("runs nothing for a selection that holds no statement", () => {
    // The semicolon between two of them: something is selected, and none of
    // it is a statement.
    expect(targetFor(SCRIPT, TEXT, { from: 8, to: 10 })).toBeNull()
  })

  it("runs the document explicitly, and says it is a script when it is one", () => {
    expect(wholeDocument(SCRIPT, TEXT)).toEqual({
      text: TEXT,
      start: 0,
      end: TEXT.length,
      scope: "script",
    })
  })

  it("calls a document of one statement a statement", () => {
    const one: PreparedScript = { statements: [SCRIPT.statements[0]!], parameters: [] }

    expect(wholeDocument(one, "select 1")?.scope).toBe("statement")
  })

  it("runs nothing when the source found no statements", () => {
    const empty: PreparedScript = { statements: [], parameters: [] }

    expect(wholeDocument(empty, "  ")).toBeNull()
    expect(targetFor(empty, "  ", caret(0))).toBeNull()
  })
})

describe("the form a query with parameters asks for", () => {
  it("fills a row from what the document remembers", () => {
    const form = parameterForm(["since"], { since: "2026-01-01" })

    expect(form).toEqual([
      { name: "since", value: "2026-01-01", isNull: false, secret: false, remember: true },
    ])
  })

  it("leaves a row nobody has answered empty and not remembered", () => {
    expect(parameterForm(["since"], {})).toEqual([
      { name: "since", value: "", isNull: false, secret: false, remember: false },
    ])
  })

  it("keeps what is already filled in when the query changes around it", () => {
    const filled = parameterForm(["since"], {})
    filled[0]!.value = "typed"

    const again = parameterForm(["since", "until"], {}, filled)

    expect(again[0]!.value).toBe("typed")
    expect(again[1]!.value).toBe("")
  })

  it("drops a row for a parameter the query no longer has", () => {
    const filled = parameterForm(["gone"], {})

    expect(parameterForm(["kept"], {}, filled).map((row) => row.name)).toEqual(["kept"])
  })

  it("reads a remembered SQL null as one", () => {
    expect(parameterForm(["maybe"], { maybe: null })[0]).toMatchObject({
      isNull: true,
      remember: true,
    })
  })

  it("sends a value or SQL null, and says which were secret", () => {
    const form = [
      { name: "a", value: "1", isNull: false, secret: false, remember: false },
      { name: "b", value: "ignored", isNull: true, secret: false, remember: false },
      { name: "c", value: "s3cret", isNull: false, secret: true, remember: false },
    ]

    expect(bindingsOf(form)).toEqual([
      { name: "a", value: "1", secret: false },
      { name: "b", value: null, secret: false },
      { name: "c", value: "s3cret", secret: true },
    ])
  })

  it("never remembers a secret, whatever the other box says", () => {
    const form = [
      { name: "a", value: "1", isNull: false, secret: false, remember: true },
      { name: "b", value: "s3cret", isNull: false, secret: true, remember: true },
      { name: "c", value: "2", isNull: false, secret: false, remember: false },
    ]

    expect(toRemember(form)).toEqual({ a: "1" })
  })

  it("is ready when every row has an answer, and null is an answer", () => {
    expect(ready([{ name: "a", value: "", isNull: true, secret: false, remember: false }])).toBe(
      true
    )
    expect(
      ready([{ name: "a", value: "", isNull: false, secret: false, remember: false }])
    ).toBe(false)
    expect(ready([])).toBe(true)
  })
})

describe("how long a run has been going", () => {
  it("reads as milliseconds, then seconds, then minutes", () => {
    expect(elapsed(120)).toBe("120 ms")
    expect(elapsed(4200)).toBe("4.2 s")
    expect(elapsed(75_000)).toBe("1m 15s")
  })
})
