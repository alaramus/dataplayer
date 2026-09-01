import { describe, expect, it } from "vitest"

import type { ExplainNode } from "@/client"

import { estimate, flatten, nodeById, share } from "./explain"

const PLAN: ExplainNode = {
  id: "0",
  kind: "Limit",
  label: "Limit",
  total_cost: 100,
  rows: 5,
  children: [
    {
      id: "0.0",
      kind: "Sort",
      label: "Sort",
      total_cost: 90,
      rows: 5,
      children: [
        {
          id: "0.0.0",
          kind: "Seq Scan",
          label: "Seq Scan on projects",
          relation: "projects",
          total_cost: 60,
          rows: 150,
          width: 496,
          children: [],
        },
      ],
    },
  ],
}

describe("a plan read as a list", () => {
  it("keeps the order the tree is drawn in, with the depth of each operation", () => {
    expect(flatten(PLAN).map((row) => [row.id, row.depth])).toEqual([
      ["0", 0],
      ["0.0", 1],
      ["0.0.0", 2],
    ])
  })

  it("finds an operation by the id both views address it with", () => {
    expect(nodeById(PLAN, "0.0.0")?.kind).toBe("Seq Scan")
    expect(nodeById(PLAN, "nowhere")).toBeNull()
  })

  it("reads an estimate as words, and leaves out what the source did not say", () => {
    expect(estimate(PLAN)).toBe("cost 100.00 · 5 rows")
    expect(estimate(nodeById(PLAN, "0.0.0") as ExplainNode)).toBe(
      "cost 60.00 · 150 rows · 496 bytes wide"
    )
    expect(estimate({ id: "x", kind: "X", label: "X" })).toBe("")
  })

  it("says what share of the plan an operation carries, and nothing when it cannot", () => {
    expect(share(nodeById(PLAN, "0.0.0") as ExplainNode, 100)).toBeCloseTo(0.6)
    expect(share(PLAN, 100)).toBe(1)
    expect(share(PLAN, 0)).toBe(0)
    expect(share({ id: "x", kind: "X", label: "X" }, 100)).toBe(0)
  })
})
