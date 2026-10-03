import { describe, expect, it } from "vitest"

import type { Location } from "./location"
import { locationFromAncestors, revealPlan, standsAt } from "./reveal"
import type { CatalogHolding } from "./reveal"

/** A catalog on the `reports` folder, holding nothing. */
const IDLE: CatalogHolding = {
  currentId: "reports",
  selectedGroups: [],
  searched: false,
  filter: "",
  ticked: 0,
  shown: ["reports/q1.csv", "reports/q2.csv"],
}

const HERE: Location = { crumbs: [{ id: "reports", label: "reports" }], groups: [], parentId: "reports" }
const DEEPER: Location = {
  crumbs: [{ id: "reports", label: "reports" }, { id: "reports/2024", label: "2024" }],
  groups: [],
  parentId: "reports/2024",
}

describe("pointing a catalog at a node (D112, D205)", () => {
  it("marks a node on the level it stands on, keeping its filter and ticks", () => {
    expect(revealPlan(IDLE, HERE, "reports/q1.csv")).toBe("mark")
    expect(revealPlan({ ...IDLE, filter: "q1", ticked: 2, shown: ["reports/q1.csv"] }, HERE, "reports/q1.csv")).toBe("mark")
  })

  it("leaves search results on its own level before it marks the row", () => {
    expect(revealPlan({ ...IDLE, searched: true, filter: "q1", shown: ["reports/2024/q1.csv"] }, HERE, "reports/q1.csv"))
      .toBe("leave-search")
  })

  it("walks a catalog that holds nothing to the node's level", () => {
    expect(revealPlan(IDLE, DEEPER, "reports/2024/q1.csv")).toBe("walk")
  })

  it("never wipes a search, a filter or ticks: another catalog shows the node", () => {
    expect(revealPlan({ ...IDLE, searched: true, filter: "q1" }, DEEPER, "reports/2024/q1.csv")).toBe("elsewhere")
    expect(revealPlan({ ...IDLE, filter: "q" }, DEEPER, "reports/2024/q1.csv")).toBe("elsewhere")
    expect(revealPlan({ ...IDLE, ticked: 1 }, DEEPER, "reports/2024/q1.csv")).toBe("elsewhere")
  })

  it("does not clear a filter that hides the node on its own level", () => {
    expect(revealPlan({ ...IDLE, filter: "q2", shown: ["reports/q2.csv"] }, HERE, "reports/q1.csv")).toBe("elsewhere")
  })

  it("counts a grouping not ticked as another level", () => {
    const schemas: CatalogHolding = { ...IDLE, currentId: null, selectedGroups: ["public"], shown: [] }
    const sales: Location = { crumbs: [], groups: ["sales"], parentId: null }
    expect(standsAt(schemas, sales)).toBe(false)
    expect(standsAt({ ...schemas, selectedGroups: ["public", "sales"] }, sales)).toBe(true)
    expect(revealPlan(schemas, sales, "sales.orders")).toBe("walk")
    expect(revealPlan({ ...schemas, filter: "ord" }, sales, "sales.orders")).toBe("elsewhere")
  })
})

describe("a node's place from the ancestors its hit carries", () => {
  it("ticks the grouping and opens every branch below it, for a key with no node path", () => {
    const ancestors = [
      { id: "d0", label: "db0" },
      { id: "f0:cache:", label: "cache:" },
      { id: "f0:cache:user:", label: "user:" },
    ]
    expect(locationFromAncestors(ancestors, ["d0", "d1"])).toEqual({
      crumbs: [{ id: "f0:cache:", label: "cache:" }, { id: "f0:cache:user:", label: "user:" }],
      groups: ["d0"],
      parentId: "f0:cache:user:",
    })
  })

  it("stands a key at the top of its database in that database's grouping", () => {
    expect(locationFromAncestors([{ id: "d3", label: "db3" }], ["d0", "d3"])).toEqual({
      crumbs: [],
      groups: ["d3"],
      parentId: null,
    })
  })
})
