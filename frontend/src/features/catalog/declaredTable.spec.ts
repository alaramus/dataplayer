import { describe, expect, it } from "vitest"

import type { TableProposal } from "@/client"
import {
  declarationOf,
  draftOf,
  draftProblem,
  foundText,
  MAX_COLUMNS,
  withField,
} from "./declaredTable"
import type { TableDraft } from "./declaredTable"

const proposal: TableProposal = {
  node_id: "f0:user:",
  name: "user",
  columns: [
    { name: "name", type: "text", ticked: true, found_in: 3 },
    { name: "age", type: "number", ticked: true, found_in: 2 },
    { name: "note", type: "text", ticked: false, found_in: 1 },
  ],
  sampled: 3,
  declared: false,
  reserved: ["key"],
}

function draft(): TableDraft {
  return draftOf(proposal)
}

describe("declaring a table over a folder", () => {
  it("starts from what the first hashes hold", () => {
    expect(draft()).toEqual({
      name: "user",
      fields: [
        { name: "name", type: "text", ticked: true, foundIn: 3 },
        { name: "age", type: "number", ticked: true, foundIn: 2 },
        { name: "note", type: "text", ticked: false, foundIn: 1 },
      ],
      sampled: 3,
      declared: false,
      reserved: ["key"],
    })
  })

  it("sends the ticked fields in the order they are listed", () => {
    const changed = draft()
    changed.name = "  users "
    changed.fields[0]!.ticked = false
    changed.fields[2]!.ticked = true
    changed.fields[2]!.type = "datetime"

    expect(declarationOf("f0:user:", changed)).toEqual({
      node_id: "f0:user:",
      name: "users",
      columns: [
        { name: "age", type: "number" },
        { name: "note", type: "datetime" },
      ],
    })
  })

  it("adds a field the sample did not reach, ticked, unless its name is taken", () => {
    const added = withField(draft(), " email ")
    expect(typeof added === "string" ? added : added.fields.at(-1)).toEqual({
      name: "email", type: "text", ticked: true, foundIn: null,
    })
    expect(withField(draft(), "  ")).toBe("Type the name of a field")
    expect(withField(draft(), "key")).toBe("key is the table's first column")
    expect(withField(draft(), "age")).toBe("age is already listed")
  })

  it("says why Save is off", () => {
    expect(draftProblem(draft())).toBeNull()
    expect(draftProblem({ ...draft(), name: " " })).toBe("Name the table")
    expect(
      draftProblem({ ...draft(), fields: draft().fields.map((field) => ({ ...field, ticked: false })) })
    ).toBe("Tick at least one field")
    const many = Array.from({ length: MAX_COLUMNS + 1 }, (_, index) => ({
      name: `f${String(index)}`, type: "text" as const, ticked: true, foundIn: null,
    }))
    expect(draftProblem({ ...draft(), fields: many })).toBe("A table holds at most 200 columns")
  })

  it("says where the sample met each field", () => {
    const [name] = draft().fields
    expect(foundText(name!, 3)).toBe("3 of 3")
    expect(foundText({ ...name!, foundIn: null }, 3)).toBe("Added")
  })
})
