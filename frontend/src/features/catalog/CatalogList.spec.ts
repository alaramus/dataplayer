import { flushPromises, mount } from "@vue/test-utils"
import { Notify, Quasar } from "quasar"
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
    representations: [{ kind: "table", title: "View as table" }],
    describable: true,
    summarizable: false,
    system: false,
    preferred: false,
    holdsNodes: false,
  }
}

const items: ListNode[] = [table("public.orders", "orders"), table("public.users", "users")]

function mountList(revealed: string | null = null, checked: string[] = []) {
  return mount(CatalogList, {
    props: { items, checked, loading: false, revealed },
    global: { plugins: [[Quasar, { plugins: { Notify } }]] },
  })
}

function report(id: string, label: string, caption: string): ListNode {
  return {
    id,
    label,
    caption,
    icon: "assessment",
    kind: "report",
    role: "leaf",
    readable: true,
    representations: [{ kind: "table", title: "View as table" }],
    describable: false,
    summarizable: false,
    system: false,
    preferred: false,
    holdsNodes: false,
  }
}

/**
 * The columns are the list's, not each row's: a row takes them with `subgrid`,
 * so names stand under names.
 *
 * The exception is a report, whose caption is a sentence the source wrote —
 * left in the shared column it would set that column's width for every row in
 * the list, so the row lays itself out instead. The class is what the
 * stylesheet keys off, so it is what this checks.
 */
/**
 * The name of a row, taken without reading it out.
 *
 * The gesture is on the icon: a control wanted only on the row under the
 * pointer must not cost every row a column of its own.
 */
describe("copying the name of a row", () => {
  it("puts the name in the clipboard", async () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
    const wrapper = mountList()

    await wrapper.get('[data-testid="catalog-copy-orders"]').trigger("click")
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith("orders")
  })

  it("does not open the row it was copied from", async () => {
    vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
    const wrapper = mountList()

    await wrapper.get('[data-testid="catalog-copy-orders"]').trigger("click")
    await flushPromises()

    expect(wrapper.emitted("open")).toBeUndefined()
  })
})

/**
 * U05: nothing in a row said what it was. The row took its name from what it
 * contained, starting with the copy button - "Copy orders orders" - and the
 * tick boxes had no name at all, so selecting, opening and copying were three
 * unlabelled things in a line.
 */
describe("what a row of the list is called", () => {
  it("names the row by what pressing it opens", () => {
    const wrapper = mountList()
    const row = wrapper.get('[data-testid="catalog-node-orders"]')

    expect(row.attributes("role")).toBe("button")
    expect(row.attributes("aria-label")).toBe("Open orders")
  })

  it("names every tick box by what it ticks", () => {
    const wrapper = mountList()

    expect(
      wrapper.get('[data-testid="catalog-check-orders"]').attributes("aria-label")
    ).toBe("Select orders")
    expect(wrapper.get('[data-testid="catalog-check-all"]').attributes("aria-label")).toBe(
      "Select everything here"
    )
  })
})

describe("the columns of a level", () => {
  it("keeps a measured row in the list's own columns", () => {
    const wrapper = mountList()
    expect(wrapper.get('[data-testid="catalog-node-orders"]').classes()).not.toContain(
      "catalog-list__row--sentence"
    )
  })

  it("lets a row whose caption is a sentence lay itself out", () => {
    const wrapper = mount(CatalogList, {
      props: {
        items: [report("system", "System", "What this server says about itself")],
        checked: [],
        loading: false,
      },
      global: { plugins: [[Quasar, { plugins: { Notify } }]] },
    })

    expect(wrapper.get('[data-testid="catalog-node-System"]').classes()).toContain(
      "catalog-list__row--sentence"
    )
  })
})

/**
 * The head counts twice: what is here, and what an action would be done to.
 *
 * The second number is only there while something is ticked — brackets saying
 * "(0 selected)" above an untouched list are noise on the one line the level
 * has to describe itself.
 */
describe("the head of a level", () => {
  it("says how much the level holds", () => {
    expect(mountList().get('[data-testid="catalog-count"]').text()).toBe("2 items")
  })

  it("adds how much of it is ticked", () => {
    const wrapper = mountList(null, ["public.orders"])
    expect(wrapper.get('[data-testid="catalog-count"]').text()).toBe("2 items (1 selected)")
  })
})

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
    expect(scroll.mock.contexts[0]).toBe(wrapper.get('[data-testid="catalog-node-orders"]').element)
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
