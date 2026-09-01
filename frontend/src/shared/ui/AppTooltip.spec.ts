import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { KeepAlive, defineComponent, h, shallowRef } from "vue"
import type { Component } from "vue"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import AppTooltip from "./AppTooltip.vue"

// Two tabs of one leaf are two components, and the leaf that keeps them is a
// third. The rule is about screens, where one file is one thing on it.
/* eslint-disable vue/one-component-per-file */

/** A button carrying a tooltip, the shape every icon button in the app has. */
const Panel = defineComponent({
  name: "Panel",
  setup: () => () =>
    h("button", { "data-testid": "follow" }, ["Go", h(AppTooltip, () => "Go to orders")]),
})

const Other = defineComponent({
  name: "Other",
  setup: () => () => h("div", "another tab"),
})

/**
 * Two tabs of one leaf, kept rather than destroyed — what the workspace does.
 */
function mountTabs() {
  const showing = shallowRef<Component>(Panel)
  const root = defineComponent({
    name: "Leaf",
    setup: () => () => h(KeepAlive, null, [h(showing.value)]),
  })
  const wrapper = mount(root, { attachTo: document.body, global: { plugins: [Quasar] } })
  return { wrapper, showing }
}

function tooltip(): Element | null {
  return document.body.querySelector(".q-tooltip")
}

/** Hover the button and wait out the tooltip's own delay. */
async function hover(): Promise<void> {
  document.body
    .querySelector('[data-testid="follow"]')
    ?.dispatchEvent(new MouseEvent("mouseenter"))
  await vi.advanceTimersByTimeAsync(500)
  await flushPromises()
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

/**
 * A tooltip belongs to the button under the pointer, and outlives it once.
 *
 * Pressing a button that opens another tab is the one gesture that raises no
 * `mouseleave`: the pointer stays where it is and the tab leaves instead. The
 * panel is kept, so nothing is unmounted, and the tooltip is teleported to the
 * body — it used to hang over whatever tab came next.
 */
describe("a tooltip whose tab is switched away from", () => {
  it("is shown while its button is on screen", async () => {
    const { wrapper } = mountTabs()
    await hover()

    expect(tooltip()?.textContent).toBe("Go to orders")
    wrapper.unmount()
  })

  it("goes away with the tab it belongs to", async () => {
    const { wrapper, showing } = mountTabs()
    await hover()

    showing.value = Other
    await flushPromises()
    // The tooltip fades rather than blinks out, exactly as it does when the
    // pointer leaves a button.
    await vi.advanceTimersByTimeAsync(500)
    await flushPromises()

    expect(tooltip()).toBeNull()
    wrapper.unmount()
  })

  it("comes back on the next hover once the tab is shown again", async () => {
    const { wrapper, showing } = mountTabs()
    await hover()
    showing.value = Other
    await flushPromises()
    await vi.advanceTimersByTimeAsync(500)

    showing.value = Panel
    await flushPromises()
    await hover()

    expect(tooltip()?.textContent).toBe("Go to orders")
    wrapper.unmount()
  })
})

/** Nothing above depends on a ref that a plain use of the kit would not set. */
describe("a tooltip that is never put away", () => {
  it("hides when the pointer leaves the button", async () => {
    const { wrapper } = mountTabs()
    await hover()

    document.body
      .querySelector('[data-testid="follow"]')
      ?.dispatchEvent(new MouseEvent("mouseleave"))
    await vi.advanceTimersByTimeAsync(500)
    await flushPromises()

    expect(tooltip()).toBeNull()
    wrapper.unmount()
  })
})
