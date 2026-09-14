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

function rules(own: DashboardPublic[], shared: DashboardPublic[]): number {
  const rail = mount(DashboardsRailNarrow, {
    props: { own, shared, currentId: null, maySetUp: true, creating: false },
    global: { plugins: [Quasar] },
  })
  const count = rail.findAll("[data-testid='rail-narrow-rule']").length
  rail.unmount()
  return count
}

describe("the rules of the narrow dashboards rail", () => {
  it("stand between the groups that show something", () => {
    expect(rules([dashboard("mine")], [dashboard("theirs", "read")])).toBe(3)
    expect(rules([dashboard("mine")], [])).toBe(2)
    expect(rules([], [dashboard("theirs", "read")])).toBe(2)
  })

  it("are one line, not two in a row, while there is no dashboard", () => {
    expect(rules([], [])).toBe(1)
  })
})
