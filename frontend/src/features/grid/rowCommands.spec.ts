import { describe, expect, it } from "vitest"

import type { FetchColumn, RowCommand } from "@/client"

import { commandOutcome, commandQuestion, commandsForRow, keyOf } from "./rowCommands"
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
const INSTALLED: FetchColumn = {
  name: "installed",
  type: { sql: "boolean", category: "boolean" },
  sortable: true,
  filter_operators: ["eq"],
}

const TERMINATE: RowCommand = {
  name: "terminate_backend",
  title: "Terminate",
  icon: "power_settings_new",
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

const at = (index: number): GridRow => ROWS[index] as GridRow

describe("what a row command is given", () => {
  it("reads the column the command named, in the row it was pressed on", () => {
    expect(keyOf(TERMINATE, [PID, STATE], at(0))).toBe("101")
    expect(keyOf(TERMINATE, [PID, STATE], at(1))).toBe("102")
  })

  it("names no row whose key is empty", () => {
    expect(keyOf(TERMINATE, [PID, STATE], at(2))).toBeNull()
  })

  it("names nothing when the page has no such column", () => {
    // The declaration and the answer disagreeing is not a reason to send
    // whatever column happens to be first.
    expect(keyOf(TERMINATE, [STATE], at(0))).toBeNull()
  })
})

describe("which commands a row is offered", () => {
  const install: RowCommand = {
    name: "install_extension",
    title: "Install",
    icon: "add",
    description: "Install this on the server",
    requires: "structure",
    identified_by: "pid",
    applies_when: { column: "installed", equals: "false" },
  }
  const remove: RowCommand = {
    ...install,
    name: "drop_extension",
    title: "Remove",
    icon: "delete",
    applies_when: { column: "installed", equals: "true" },
  }
  const columns = [PID, INSTALLED]
  const installed: GridRow = { id: "0", values: ["citext", "true"] }
  const absent: GridRow = { id: "1", values: ["bloom", "false"] }

  it("offers only the one the row's own value admits", () => {
    // An extension is installed or removed, never both, and the row already
    // says which: nothing here knows what `installed` means.
    expect(commandsForRow([install, remove], columns, installed)).toEqual([remove])
    expect(commandsForRow([install, remove], columns, absent)).toEqual([install])
  })

  it("offers a command that names no condition on every row it can name", () => {
    expect(commandsForRow([TERMINATE], [PID, STATE], at(0))).toEqual([TERMINATE])
    expect(commandsForRow([TERMINATE], [PID, STATE], at(2))).toEqual([])
  })

  it("offers nothing when the page has no column the condition is about", () => {
    expect(commandsForRow([install, remove], [PID], installed)).toEqual([])
  })
})

describe("what the confirmation asks", () => {
  it("names the row it is about", () => {
    expect(commandQuestion(TERMINATE, "101")).toBe("Terminate 101?")
  })
})

describe("what is said afterwards", () => {
  it("passes on the source's own sentence", () => {
    expect(commandOutcome({ message: "1 process closed", refused: [] })).toEqual({
      text: "1 process closed",
      failed: false,
    })
  })

  it("adds what the source would not do, and calls that a failure", () => {
    expect(
      commandOutcome({
        message: "0 of 1 processes closed",
        refused: ["101 is no longer running"],
      })
    ).toEqual({
      text: "0 of 1 processes closed. 101 is no longer running",
      failed: true,
    })
  })

  it("reads an answer that left the list out", () => {
    expect(commandOutcome({ message: "1 process closed" }).failed).toBe(false)
  })
})
