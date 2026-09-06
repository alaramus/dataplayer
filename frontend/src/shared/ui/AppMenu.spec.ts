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

  it("says why it cannot be used, under its label", async () => {
    await open([
      { name: "delete", label: "Delete", disable: true, hint: "Tick a row to use this" },
    ])

    expect(line("delete")).toContain("Delete")
    expect(line("delete")).toContain("Tick a row to use this")
  })

  it("says nothing extra when it can be used", async () => {
    await open([{ name: "upload", label: "Upload" }])

    expect(line("upload").trim()).toBe("Upload")
  })
})
