import { describe, expect, it } from "vitest"

import { chartViewKey } from "./view"

describe("a chart view identity", () => {
  const request = {
    node_id: "public.orders",
    limit: 100,
    offset: 0,
    filters: [{ column: "state", op: "eq" as const, value: "open" }],
    sort: [{ column: "created_at", descending: true }],
  }

  it("is stable for the same complete bounded view", () => {
    expect(chartViewKey("c1", request, ["state", "total"])).toBe(
      chartViewKey("c1", request, ["state", "total"])
    )
  })

  it("changes with the page, query, visible order or connection", () => {
    const key = chartViewKey("c1", request, ["state", "total"])
    expect(chartViewKey("c1", { ...request, offset: 100 }, ["state", "total"])).not.toBe(key)
    expect(chartViewKey("c1", request, ["total", "state"])).not.toBe(key)
    expect(chartViewKey("c2", request, ["state", "total"])).not.toBe(key)
  })
})
