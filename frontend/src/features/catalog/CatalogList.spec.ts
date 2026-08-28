import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"

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
    describable: true,
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
  it("does not put a structure command in catalog rows", () => {
    const wrapper = mountList()
    expect(wrapper.find('[data-testid="catalog-structure-orders"]').exists()).toBe(false)
  })

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

  /**
   * The row may be below the fold: the level is arrived at from a tab, so
   * nobody scrolled to it by hand. jsdom has no layout and therefore no
   * `scrollIntoView` of its own — `vitest.setup.ts` gives it one, or this
   * would be a call into nothing.
   */
  it("brings the row into view", async () => {
    const scroll = vi.spyOn(Element.prototype, "scrollIntoView")
    const wrapper = mountList("public.orders")
    await flushPromises()
    expect(scroll).toHaveBeenCalledWith({ block: "nearest" })
    expect(scroll.mock.contexts[0]).toBe(
      wrapper.get('[data-testid="catalog-node-orders"]').element
    )
  })

  it("brings nothing into view when nobody was pointed at", async () => {
    const scroll = vi.spyOn(Element.prototype, "scrollIntoView")
    mountList()
    await flushPromises()
    expect(scroll).not.toHaveBeenCalled()
  })

  // The level may not hold the node at all — arrived at from a table opened
  // before the user walked elsewhere. Nothing is marked, and nothing breaks.
  it("marks nothing when the row asked for is not on this level", () => {
    const wrapper = mountList("some.other.node")
    expect(wrapper.findAll("[data-revealed]")).toHaveLength(0)
  })
})
