import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"

import { withWindowHost } from "@/shared/testing/windows"

import CellValueDialog from "./CellValueDialog.vue"

describe("the full cell viewer", () => {
  it("shows and copies the complete untruncated value", async () => {
    vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
    const value = '{"description":"the complete value"}'
    const wrapper = mount(
      withWindowHost(CellValueDialog, {
        modelValue: true,
        columnName: "payload",
        typeSql: "jsonb",
        value,
      }),
      {
      global: { plugins: [Quasar] },
      attachTo: document.body,
      }
    )
    await flushPromises()

    expect(document.body.textContent).toContain(value)
    const copy = document.body.querySelector<HTMLElement>('[data-testid="grid-viewer-copy"]')
    expect(copy).not.toBeNull()
    copy?.click()
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith(value)
    wrapper.unmount()
  })
})
