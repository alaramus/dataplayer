import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import type { DashboardPublic } from "@/client"
import DashboardsRailNarrow from "./DashboardsRailNarrow.vue"

function dashboard(name: string, access: DashboardPublic["access"] = "own"): DashboardPublic {
  return {
    id: name,
    name,
    version: 1,
    updated_at: "2026-09-14T00:00:00Z",
    access,
    widgets: [],
  }
}

function mountRail(own: DashboardPublic[], shared: DashboardPublic[]) {
  return mount(DashboardsRailNarrow, {
    props: { own, shared, currentId: null, maySetUp: true, creating: false },
    global: { plugins: [Quasar] },
  })
}

function rules(own: DashboardPublic[], shared: DashboardPublic[]): number {
  const rail = mountRail(own, shared)
  const count = rail.findAll("[data-testid='rail-narrow-rule']").length
  rail.unmount()
  return count
}

describe("the head of the narrow dashboards rail", () => {
  it("holds the plus and nothing else", () => {
    const rail = mountRail([dashboard("mine")], [dashboard("theirs", "read")])
    const head = rail.get("[data-testid='dashboards-rail-head']")
    expect(head.findAll("button")).toHaveLength(1)
    expect(head.get("button").attributes("data-testid")).toBe("dashboard-new")
    rail.unmount()
  })
})

describe("the rules of the narrow dashboards rail", () => {
  it("stand between the groups that show something", () => {
    expect(rules([dashboard("mine")], [dashboard("theirs", "read")])).toBe(2)
    expect(rules([dashboard("mine")], [])).toBe(1)
    expect(rules([], [dashboard("theirs", "read")])).toBe(1)
  })

  it("stand nowhere while there is no dashboard: the head's line is under the plus", () => {
    expect(rules([], [])).toBe(0)
  })
})
