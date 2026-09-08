import { describe, expect, it } from "vitest"

import type { PreparedScript, QueryRehearsal } from "@/client"

import { blockedReason, invalidationsFor, needsRehearsal, rehearsalReport } from "./structure"

function script(...statements: Partial<PreparedScript["statements"][number]>[]): PreparedScript {
  return {
    statements: statements.map((statement, ordinal) => ({
      ordinal,
      start: 0,
      end: 1,
      text: "",
      kind: "ddl",
      risk: "high",
      destructive: false,
      refused: null,
      parameters: [],
      targets: [],
      ...statement,
    })),
    parameters: [],
  } as PreparedScript
}

describe("what has to be tried out first", () => {
  it("asks for a rehearsal when something cannot be undone", () => {
    expect(needsRehearsal(script({ destructive: true }))).toBe(true)
  })

  it("does not ask for one when nothing is destructive", () => {
    expect(needsRehearsal(script({ destructive: false }))).toBe(false)
    expect(needsRehearsal(null)).toBe(false)
  })
})

describe("what the rehearsal is reported as", () => {
  it("keeps the source's own words about what would go", () => {
    const rehearsal: QueryRehearsal = {
      statements: [
        {
          ordinal: 0,
          outcome: "ok",
          command_tag: "DROP TABLE",
          affected_rows: null,
          notices: [{ severity: "NOTICE", message: "drop cascades to view monthly" }],
          diagnostic: null,
        },
      ],
      blocked: false,
      runnable: true,
      effect: { scope: "nodes", reload_node_ids: [], relation_node_ids: [] },
    }

    const report = rehearsalReport(rehearsal)

    expect(report).toContain("DROP TABLE")
    expect(report).toContain("drop cascades to view monthly")
  })

  it("says when the source refused it", () => {
    const rehearsal: QueryRehearsal = {
      statements: [
        {
          ordinal: 0,
          outcome: "failed",
          command_tag: null,
          affected_rows: null,
          notices: [],
          diagnostic: {
            code: "2BP01",
            category: "unknown",
            message: "other objects depend on it",
            position: null,
            hint: null,
          },
        },
      ],
      blocked: false,
      runnable: false,
      effect: { scope: "nodes", reload_node_ids: [], relation_node_ids: [] },
    }

    expect(rehearsalReport(rehearsal)).toContain("other objects depend on it")
  })

  it("stops a run when the rehearsal was blocked", () => {
    const blocked: QueryRehearsal = {
      statements: [],
      blocked: true,
      runnable: false,
      effect: { scope: "nodes", reload_node_ids: [], relation_node_ids: [] },
    }

    expect(blockedReason(blocked)).toContain("holding a lock")
    expect(blockedReason({ ...blocked, blocked: false })).toBeNull()
  })
})

describe("what a committed change makes untrue", () => {
  it("drops the branches and relations the source named", () => {
    const keys = invalidationsFor(
      {
        scope: "nodes",
        reload_node_ids: ["demo_lab"],
        relation_node_ids: ["demo_lab.t"],
      },
      "c1"
    )

    expect(keys).toContainEqual(["catalog", "c1", "demo_lab"])
    expect(keys).toContainEqual(["relationModel", "c1", "demo_lab.t"])
    expect(keys).toContainEqual(["rows", "c1"])
    expect(keys).toContainEqual(["connectors", "c1", "features"])
  })

  it("drops the whole connection when the source could not be exact", () => {
    const keys = invalidationsFor(
      { scope: "connection", reload_node_ids: [], relation_node_ids: [] },
      "c1"
    )

    expect(keys).toContainEqual(["catalog", "c1"])
    expect(keys).toContainEqual(["relationModel", "c1"])
    expect(keys).toContainEqual(["connectors", "c1", "features"])
  })

  it("drops nothing when nothing changed", () => {
    expect(invalidationsFor(null, "c1")).toEqual([])
  })
})
