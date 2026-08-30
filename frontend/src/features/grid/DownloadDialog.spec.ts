import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Quasar } from "quasar"
import { afterEach, describe, expect, it } from "vitest"

import DownloadDialog from "./DownloadDialog.vue"

function mountDialog(allSupported: boolean) {
  return mount(DownloadDialog, {
    props: {
      modelValue: true,
      pageRange: "Rows 101–200",
      columnCount: 3,
      filterCount: 2,
      allSupported,
      allReason: "Only this page can be downloaded",
      running: false,
    },
    global: { plugins: [[Quasar, { plugins: { Dialog } }]] },
  })
}

afterEach(() => {
  document.body.querySelectorAll(".q-dialog").forEach((dialog) => dialog.remove())
})

describe("download scopes", () => {
  it("chooses every matching row explicitly", async () => {
    const wrapper = mountDialog(true)
    await flushPromises()

    document.body.querySelector<HTMLElement>('[data-testid="download-scope-all"]')?.click()
    document.body.querySelector<HTMLElement>('[data-testid="grid-download-run"]')?.click()

    expect(wrapper.emitted("run")?.[0]).toEqual(["all"])
    wrapper.unmount()
  })

  it("keeps the whole-row scope unavailable when the source cannot stream it", async () => {
    const wrapper = mountDialog(false)
    await flushPromises()

    const all = document.body.querySelector<HTMLButtonElement>(
      '[data-testid="download-scope-all"]'
    )
    expect(all?.disabled).toBe(true)
    expect(document.body.textContent).toContain("Only this page can be downloaded")
    wrapper.unmount()
  })
})
