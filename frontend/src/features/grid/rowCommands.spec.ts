import { describe, expect, it } from "vitest"

import type { FetchColumn, RowCommand } from "@/client"

import { commandOutcome, commandQuestion, keysOf } from "./rowCommands"
import type { GridRow } from "./types"

const PID: FetchColumn = {
  name: "pid",
  type: { sql: "integer", category: "number" },
  sortable: true,
  filter_operators: ["eq"],
}
const STATE: FetchColumn = {
  name: "state",
  type: { sql: "text", category: "string" },
  sortable: true,
  filter_operators: ["eq"],
}

const TERMINATE: RowCommand = {
  name: "terminate_backend",
  title: "Terminate",
  description: "Close the connection",
  destructive: true,
  requires: "structure",
  identified_by: "pid",
}

const ROWS: GridRow[] = [
  { id: "0", values: ["101", "active"] },
  { id: "1", values: ["102", "idle"] },
  { id: "2", values: [null, "idle"] },
]

describe("what a row command is given", () => {
  it("reads the column the command named, for the rows that are ticked", () => {
    expect(keysOf(TERMINATE, [PID, STATE], ROWS, [1, 0])).toEqual(["101", "102"])
  })

  it("offers nothing when nothing is ticked", () => {
    expect(keysOf(TERMINATE, [PID, STATE], ROWS, [])).toEqual([])
  })

  it("leaves out a row whose key is empty", () => {
    expect(keysOf(TERMINATE, [PID, STATE], ROWS, [2])).toEqual([])
  })

  it("names a row once however many of its cells are in the selection", () => {
    expect(keysOf(TERMINATE, [PID, STATE], ROWS, [0, 0])).toEqual(["101"])
  })

  it("offers nothing when the page has no such column", () => {
    // The declaration and the answer disagreeing is not a reason to send
    // whatever column happens to be first.
    expect(keysOf(TERMINATE, [STATE], ROWS, [0, 1])).toEqual([])
  })
})

describe("what the confirmation asks", () => {
  it("names the row when there is one", () => {
    expect(commandQuestion(TERMINATE, ["101"])).toBe("Terminate 101?")
  })

  it("counts them when there are several", () => {
    expect(commandQuestion(TERMINATE, ["101", "102"])).toBe("Terminate 2 rows?")
  })
})

describe("what is said afterwards", () => {
  it("passes on the source's own sentence", () => {
    expect(commandOutcome({ message: "2 processes closed", refused: [] })).toEqual({
      text: "2 processes closed",
      failed: false,
    })
  })

  it("adds what the source would not do, and calls that a failure", () => {
    expect(
      commandOutcome({
        message: "1 of 2 processes closed",
        refused: ["102 is no longer running"],
      })
    ).toEqual({
      text: "1 of 2 processes closed. 102 is no longer running",
      failed: true,
    })
  })

  it("reads an answer that left the list out", () => {
    expect(commandOutcome({ message: "1 process closed" }).failed).toBe(false)
  })
})
