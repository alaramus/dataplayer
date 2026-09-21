import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import { withWindowHost } from "@/shared/testing/windows"

import DownloadDialog from "./DownloadDialog.vue"

function mountDialog(allSupported: boolean) {
  return mount(
    withWindowHost(DownloadDialog, {
      modelValue: true,
      pageRange: "Rows 101–200",
      columnCount: 3,
      filterCount: 2,
      allSupported,
      allReason: "Only this page can be downloaded",
      running: false,
    }),
    { global: { plugins: [[Quasar, { plugins: { Dialog } }]] } }
  )
}

describe("download scopes", () => {
  it("chooses every matching row explicitly", async () => {
    const wrapper = mountDialog(true)
    await flushPromises()

    document.body.querySelector<HTMLElement>('[data-testid="download-scope-all"]')?.click()
    document.body.querySelector<HTMLElement>('[data-testid="grid-download-run"]')?.click()

    expect(wrapper.findComponent(DownloadDialog).emitted("run")?.[0]).toEqual([
      "all",
      "browser",
    ])
    wrapper.unmount()
  })

  it("says where it is going as well as how much of it", async () => {
    // The two used to happen together, so a person who wanted the file got a
    // copy in their own files as litter, and the other way round.
    const wrapper = mountDialog(true)
    await flushPromises()

    document.body.querySelector<HTMLElement>('[data-testid="grid-download-keep"]')?.click()

    expect(wrapper.findComponent(DownloadDialog).emitted("run")?.[0]).toEqual([
      "page",
      "files",
    ])
    wrapper.unmount()
  })

  it("keeps the whole-row scope unavailable when the source cannot stream it", async () => {
    const wrapper = mountDialog(false)
    await flushPromises()

    const all = document.body.querySelector<HTMLElement>('[data-testid="download-scope-all"]')
    expect(all?.getAttribute("aria-disabled")).toBe("true")
    expect(document.body.textContent).toContain("Only this page can be downloaded")
    all?.click()
    document.body.querySelector<HTMLElement>('[data-testid="grid-download-run"]')?.click()
    expect(wrapper.findComponent(DownloadDialog).emitted("run")?.[0]).toEqual(["page", "browser"])
    wrapper.unmount()
  })
})
