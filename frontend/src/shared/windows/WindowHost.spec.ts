import { DOMWrapper, flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent, h, onMounted, ref } from "vue"
import { describe, expect, it, vi } from "vitest"

import { first } from "@/shared/testing/collections"

import WindowHost from "./WindowHost.vue"
import WindowTaskbar from "./WindowTaskbar.vue"
import { useWindows } from "./useWindows"
import type { WindowsApi } from "./useWindows"

describe("the window frame and footer manager", () => {
  it.each([false, true])("moves focus into a newly opened window, preserving field focus: %s", async (focusField) => {
    const Draft = defineComponent({
      setup() {
        const input = ref<HTMLInputElement | null>(null)
        onMounted(() => {
          if (focusField) input.value?.focus()
        })
        return () => h("input", { ref: input, "aria-label": "Draft" })
      },
    })
    const Root = defineComponent({
      setup() {
        const windows = useWindows()
        return () => h("main", [
          h("button", {
            onClick: () => windows.open({
              id: "draft", look: { title: "New connection" },
              size: { width: 400, height: 300 }, component: Draft, autoFit: false,
            }),
          }, "Open window"),
          h(WindowHost, { context: windows.context }),
        ])
      },
    })
    const wrapper = mount(Root, { attachTo: document.body, global: { plugins: [Quasar] } })
    try {
      const opener = wrapper.get("button")
      opener.element.focus()
      await opener.trigger("click")
      await flushPromises()
      const frame = document.body.querySelector<HTMLElement>('[data-testid="window-draft"]')!
      expect(document.activeElement).toBe(focusField ? frame.querySelector("input") : frame)
      expect(frame.getAttribute("aria-label")).toBe("New connection")
      expect(frame.getAttribute("aria-modal")).not.toBe("true")
    } finally {
      wrapper.unmount()
    }
  })

  it("restores the same live draft through the footer and preserves its size mode", async () => {
    const mounted = vi.fn()
    const Draft = defineComponent({
      setup() {
        mounted()
        const value = ref("")
        return () => h("input", {
          "aria-label": "Draft",
          value: value.value,
          onInput: (event: Event) => { value.value = (event.target as HTMLInputElement).value },
        })
      },
    })
    let windows: WindowsApi
    const Root = defineComponent({
      setup() {
        windows = useWindows()
        windows.open({
          id: "draft", look: { title: "New connection" },
          size: { width: 400, height: 300 }, component: Draft, autoFit: false,
        })
        windows.setBottomInset(55)
        return () => h("main", [
          h(WindowHost, { context: windows.context }),
          h(WindowTaskbar, { context: windows.context }),
        ])
      },
    })
    const wrapper = mount(Root, { attachTo: document.body, global: { plugins: [Quasar] } })
    try {
      // The host teleports its frames to the body: stubbing the teleport away
      // rebuilds the subtree on every render, which is exactly what the draft
      // below is here to prove does not happen.
      const frame = new DOMWrapper(
        document.body.querySelector<HTMLElement>('[data-testid="window-draft"]')!
      )
      const normal = first(windows!.context.windows.value).rect
      await frame.get('input[aria-label="Draft"]').setValue("Keep this unsaved value")
      await frame.get('[aria-label="Maximize"]').trigger("click")
      expect(frame.attributes("style")).toContain("100dvh - 55px")
      expect(frame.find('[data-testid="window-resize-bottom-right-draft"]').exists()).toBe(false)

      await frame.get('[aria-label="Minimize"]').trigger("click")
      await flushPromises()
      expect(frame.isVisible()).toBe(false)
      const tab = wrapper.get('[aria-label="New connection"]')
      expect(document.activeElement).toBe(tab.element)

      windows!.rename("draft", "saved", { title: "Renamed connection", icon: "storage" })
      await flushPromises()
      expect(wrapper.find('[data-testid="window-tab-draft"]').exists()).toBe(false)
      await wrapper.get('[aria-label="Renamed connection"]').trigger("click")
      await flushPromises()
      expect(frame.isVisible()).toBe(true)
      expect(document.activeElement).toBe(frame.element)
      // The bar keeps the window once it is back: it lists what is open, not
      // what has been put aside.
      expect(wrapper.find('[data-testid="window-tab-saved"]').exists()).toBe(true)
      expect(mounted).toHaveBeenCalledOnce()
      expect((frame.get('input[aria-label="Draft"]').element as HTMLInputElement).value)
        .toBe("Keep this unsaved value")
      expect(frame.find('[aria-label="Restore size"]').exists()).toBe(true)

      await frame.get('[data-testid="window-bar-saved"]').trigger("dblclick")
      expect(frame.attributes("style")).toContain(`width: ${normal.width}px`)
      expect(frame.find('[data-testid="window-resize-bottom-right-saved"]').exists()).toBe(true)
      await frame.get('[aria-label="Close window"]').trigger("click")
      await flushPromises()
      expect(document.body.querySelector('[role="dialog"]')).toBeNull()
    } finally {
      wrapper.unmount()
    }
  })

  it("lists an open window and closes it from the bar", async () => {
    let windows: WindowsApi
    const Root = defineComponent({
      setup() {
        windows = useWindows()
        windows.open({
          id: "rows",
          look: { title: "orders" },
          size: { width: 300, height: 200 },
          component: defineComponent({ setup: () => () => h("div", "rows") }),
          autoFit: false,
        })
        return () => h("main", [
          h(WindowHost, { context: windows.context }),
          h(WindowTaskbar, { context: windows.context }),
        ])
      },
    })
    const wrapper = mount(Root, { attachTo: document.body, global: { plugins: [Quasar] } })
    try {
      // On the bar from the moment it opens, not only once it is put aside.
      expect(wrapper.find('[data-testid="window-tab-rows"]').exists()).toBe(true)

      // The window one is looking at goes away when its own button is pressed,
      // and comes back the next time.
      await wrapper.get('[data-testid="window-tab-rows"]').trigger("click")
      await flushPromises()
      expect(first(windows!.context.windows.value).minimized).toBe(true)
      await wrapper.get('[data-testid="window-tab-rows"]').trigger("click")
      await flushPromises()
      expect(first(windows!.context.windows.value).minimized).toBe(false)

      await wrapper.get('[data-testid="window-tab-close-rows"]').trigger("click")
      await flushPromises()
      expect(windows!.context.windows.value).toEqual([])
      expect(wrapper.find('[data-testid="window-taskbar"]').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })

  it("draws a window's own command before the ones every window has", async () => {
    // Returning a detached panel to the workspace is about the frame, the way
    // minimize and close are, so a feature declares it here rather than
    // drawing a second row of buttons inside the window (D112).
    const run = vi.fn()
    const Root = defineComponent({
      setup() {
        const windows = useWindows()
        windows.open({
          id: "held",
          look: { title: "Orders" },
          size: { width: 300, height: 200 },
          component: defineComponent({ setup: () => () => h("div", "rows") }),
          autoFit: false,
          actions: [
            { icon: "tab", tooltip: "Return to panel", testid: "dock-panel", run },
          ],
        })
        return () => h("main", [h(WindowHost, { context: windows.context })])
      },
    })
    const wrapper = mount(Root, { attachTo: document.body, global: { plugins: [Quasar] } })
    try {
      const frame = new DOMWrapper(
        document.body.querySelector<HTMLElement>('[data-testid="window-held"]')!
      )
      const buttons = frame.findAll('[data-testid="window-bar-held"] button')
      const labels = buttons.map((button) => button.attributes("aria-label"))

      expect(labels).toEqual(["Return to panel", "Minimize", "Maximize", "Close window"])

      await frame.get('[data-testid="dock-panel"]').trigger("click")
      expect(run).toHaveBeenCalledOnce()
    } finally {
      wrapper.unmount()
    }
  })
})
