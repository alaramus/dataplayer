import { describe, expect, it } from "vitest"

import { makeLeaf } from "@/shared/workspace/model"
import { serializeWorkspace } from "@/shared/workspace/persist"

import {
  groupNameProblem,
  groupsUnavailableIn,
  parseGroups,
  serializeGroups,
  suggestedGroupName,
  validGroupSnapshot,
} from "./groups"
import { groupFixture } from "./testing/tabGroups"

describe("where tab groups can be used", () => {
  it("is Data alone, and every other space says why not", () => {
    expect(groupsUnavailableIn("data")).toBeNull()
    for (const space of ["dashboards", "ai", "pipelines"] as const) {
      expect(groupsUnavailableIn(space)).toBe("tab groups keep the tabs of Data")
    }
  })
})

describe("saved tab group data", () => {
  it("round trips several independently saved layouts", () => {
    const groups = [
      { id: "one", name: "Queries", snapshot: groupFixture().snapshot },
      { id: "two", name: "Empty", snapshot: groupFixture(false).snapshot },
    ]
    expect(parseGroups(serializeGroups(groups))).toEqual(groups)
    expect(parseGroups(null)).toEqual([])
  })

  it("rejects unknown versions, malformed layouts and duplicate identities", () => {
    const group = { id: "one", name: "Queries", snapshot: groupFixture().snapshot }
    expect(parseGroups("broken")).toBeNull()
    expect(parseGroups(JSON.stringify({ version: 2, groups: [group] }))).toBeNull()
    expect(parseGroups(serializeGroups([{ ...group, snapshot: "broken" }]))).toBeNull()
    expect(parseGroups(serializeGroups([group, { ...group, name: "Another" }]))).toBeNull()
    expect(parseGroups(serializeGroups([group, { ...group, id: "two", name: "QUERIES" }]))).toBeNull()
  })

  it("requires the fixed panel and pinned roles, and checks what each section accepts", () => {
    const { tree, panels } = groupFixture()
    expect(validGroupSnapshot(serializeWorkspace(makeLeaf("work", ["queries"], { accepts: "work" }), [panels[1]!]))).toBe(false)
    tree.children[2] = makeLeaf("work", ["queries"], { accepts: "navigate", pinned: true })
    expect(validGroupSnapshot(serializeWorkspace(tree, panels))).toBe(false)
  })

  it("requires a usable name and treats case and surrounding spaces as the same name", () => {
    const groups = [{ id: "one", name: "Queries", snapshot: groupFixture().snapshot }]
    expect(groupNameProblem("  ", groups)).toBe("Enter a group name.")
    expect(groupNameProblem("x".repeat(81), groups)).toBe("Use at most 80 characters.")
    expect(groupNameProblem(" queries ", groups)).toBe("A group with this name already exists.")
    expect(groupNameProblem(" Queries ", groups, "one")).toBe("")
  })

  it("offers a free name, stepping past the ones already taken however they are written", () => {
    const snapshot = groupFixture().snapshot
    const named = (names: string[]) => names.map((name, index) => ({ id: String(index), name, snapshot }))
    expect(suggestedGroupName([])).toBe("new group")
    expect(suggestedGroupName(named(["Queries"]))).toBe("new group")
    expect(suggestedGroupName(named([" New Group "]))).toBe("new group(1)")
    expect(suggestedGroupName(named(["new group", "new group(1)"]))).toBe("new group(2)")
    // A gap is filled rather than stepped over: the number is which name is
    // free, not how many groups there have ever been.
    expect(suggestedGroupName(named(["new group", "new group(2)"]))).toBe("new group(1)")
    // And whatever is offered is a name the dialog will accept.
    const taken = named(["new group", "new group(1)", "new group(2)"])
    expect(groupNameProblem(suggestedGroupName(taken), taken)).toBe("")
  })
})
