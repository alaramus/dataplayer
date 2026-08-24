import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import CatalogList from "./CatalogList.vue"
import type { ListNode } from "./nodes"

function table(id: string, label: string): ListNode {
  return {
    id,
    label,
    icon: "table_chart",
    kind: "table",
    role: "leaf",
    readable: true,
    system: false,
  }
}

const items: ListNode[] = [table("public.orders", "orders"), table("public.users", "users")]

function mountList(revealed: string | null = null) {
  return mount(CatalogList, {
    props: { items, checked: [], loading: false, revealed },
    global: { plugins: [Quasar] },
  })
}

/**
 * Being pointed at a row is not the same as ticking it.
 *
 * A tick means "an action will be done to this"; being revealed means "here it
 * is", after arriving from the tab of a table. Two meanings, so two marks —
 * and the second is an outline rather than a fill, or it would read as the
 * first.
 */
describe("a row that was pointed at", () => {
  it("marks the row that was asked for", () => {
    const wrapper = mountList("public.orders")
    expect(wrapper.get('[data-testid="catalog-node-orders"]').attributes("data-revealed")).toBe(
      "true"
    )
  })

  it("marks nothing else", () => {
    const wrapper = mountList("public.orders")
    expect(
      wrapper.get('[data-testid="catalog-node-users"]').attributes("data-revealed")
    ).toBeUndefined()
  })

  it("marks nothing when nobody was pointed at", () => {
    const wrapper = mountList()
    expect(
      wrapper.get('[data-testid="catalog-node-orders"]').attributes("data-revealed")
    ).toBeUndefined()
  })

  // The level may not hold the node at all — arrived at from a table opened
  // before the user walked elsewhere. Nothing is marked, and nothing breaks.
  it("marks nothing when the row asked for is not on this level", () => {
    const wrapper = mountList("some.other.node")
    expect(wrapper.findAll("[data-revealed]")).toHaveLength(0)
  })
})
