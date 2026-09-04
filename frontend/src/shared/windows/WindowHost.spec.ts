import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent, h, ref } from "vue"
import { describe, expect, it, vi } from "vitest"

import { first } from "@/shared/testing/collections"

import WindowHost from "./WindowHost.vue"
import WindowTaskbar from "./WindowTaskbar.vue"
import { useWindows } from "./useWindows"
import type { WindowsApi } from "./useWindows"

describe("the window frame and footer manager", () => {
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
    const wrapper = mount(Root, {
      attachTo: document.body,
      global: { plugins: [Quasar], stubs: { teleport: true } },
    })
    try {
      const frame = wrapper.get('[data-testid="window-draft"]')
      const normal = first(windows!.context.windows.value).rect
      await wrapper.get('input[aria-label="Draft"]').setValue("Keep this unsaved value")
      await frame.get('[aria-label="Maximize"]').trigger("click")
      expect(frame.attributes("style")).toContain("100dvh - 55px")
      expect(frame.find('[data-testid="window-resize-bottom-right-draft"]').exists()).toBe(false)

      await frame.get('[aria-label="Minimize"]').trigger("click")
      await flushPromises()
      expect(frame.isVisible()).toBe(false)
      const restore = wrapper.get('[aria-label="Restore New connection"]')
      expect(document.activeElement).toBe(restore.element)

      windows!.rename("draft", "saved", { title: "Renamed connection", icon: "storage" })
      await flushPromises()
      expect(wrapper.find('[data-testid="window-restore-draft"]').exists()).toBe(false)
      await wrapper.get('[aria-label="Restore Renamed connection"]').trigger("click")
      await flushPromises()
      expect(frame.isVisible()).toBe(true)
      expect(document.activeElement).toBe(frame.element)
      expect(wrapper.find('[aria-label="Minimized windows"]').exists()).toBe(false)
      expect(mounted).toHaveBeenCalledOnce()
      expect((wrapper.get('input[aria-label="Draft"]').element as HTMLInputElement).value)
        .toBe("Keep this unsaved value")
      expect(frame.find('[aria-label="Restore size"]').exists()).toBe(true)

      await frame.get('[data-testid="window-bar-saved"]').trigger("dblclick")
      expect(frame.attributes("style")).toContain(`width: ${normal.width}px`)
      expect(frame.find('[data-testid="window-resize-bottom-right-saved"]').exists()).toBe(true)
      await frame.get('[aria-label="Close window"]').trigger("click")
      await flushPromises()
      expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })
})
