import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent, h } from "vue"
import { afterEach, describe, expect, it } from "vitest"

import AppMenu from "./AppMenu.vue"
import type { MenuItem } from "./AppMenu.vue"

/**
 * The reason a line cannot be used has to reach the screen, not just the data.
 *
 * A menu is a Quasar popup: it needs something to hang off and draws into the
 * body rather than into the component. A hint computed and never rendered is
 * exactly the failure the catalog's captions were — they had no prop to render
 * into, and the unit test that built them was green throughout.
 *
 * Whether the tooltip actually opens over a disabled line is a question about
 * pointer events, which jsdom does not have: that half is a Playwright
 * scenario in `actions.spec.ts`.
 */
let host: ReturnType<typeof mount> | null = null

async function open(items: MenuItem[]) {
  const anchor = defineComponent({
    name: "Anchor",
    setup: () => () => h("button", [h(AppMenu, { items, modelValue: true })]),
  })
  host = mount(anchor, { attachTo: document.body, global: { plugins: [Quasar] } })
  await flushPromises()
  return host
}

function line(name: string): string {
  return document.body.querySelector(`[data-testid="menu-item-${name}"]`)?.textContent ?? ""
}

describe("a menu line", () => {
  afterEach(() => {
    host?.unmount()
    host = null
  })

  it("carries the reason it cannot be used, without saying it out loud", async () => {
    await open([
      { name: "delete", label: "Delete", disable: true, hint: "Tick a row to use this" },
    ])

    // The label reads as the label. The reason is a tooltip, which Quasar
    // renders only once something hovers it.
    expect(line("delete").trim()).toBe("Delete")
    expect(document.body.querySelector('[data-testid="menu-item-delete"] .q-tooltip'))
      .toBeNull()
  })

  it("refuses to report a selection nobody could make", async () => {
    // The label takes the pointer back so the tooltip can open, which puts a
    // clickable target inside an item that is meant to be inert.
    const wrapper = await open([{ name: "delete", label: "Delete", disable: true }])
    const item = document.body.querySelector('[data-testid="menu-item-delete"]')

    item?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    await flushPromises()

    expect(wrapper.findComponent(AppMenu).emitted("select")).toBeUndefined()
  })

  it("reports one that can be made", async () => {
    const wrapper = await open([{ name: "upload", label: "Upload" }])
    const item = document.body.querySelector('[data-testid="menu-item-upload"]')

    item?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    await flushPromises()

    expect(wrapper.findComponent(AppMenu).emitted("select")).toEqual([["upload"]])
  })
})
