import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"

import { withWindowHost } from "@/shared/testing/windows"

import SshKeyDialog from "./SshKeyDialog.vue"

vi.mock("./api", () => ({
  useGenerateSshKey: () => ({ mutateAsync: vi.fn(async () => ({ id: "key-1" })), isPending: { value: false } }),
  useImportSshKey: () => ({ mutateAsync: vi.fn(async () => ({ id: "key-2" })), isPending: { value: false } }),
}))

describe("making a key for a form", () => {
  it("hands the new key's id to the form pointing at it", async () => {
    const wrapper = mount(withWindowHost(SshKeyDialog, {
      modelValue: true,
      mode: "generate",
    }), { global: { plugins: [[Quasar, { plugins: { Dialog, Notify } }]] } })
    await flushPromises()

    // WindowDialog teleports to the body, as the BackupsDialog scenario reads.
    const name = document.body.querySelector<HTMLInputElement>('[data-testid="ssh-key-name"]')!
    name.value = "deploy"
    name.dispatchEvent(new Event("input"))
    await nextTick()
    document.body
      .querySelector('[data-testid="ssh-key-save"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    await flushPromises()

    const dialog = wrapper.findComponent(SshKeyDialog)
    expect(dialog.emitted("created")).toEqual([["key-1"]])
    expect(dialog.emitted("update:modelValue")).toContainEqual([false])
    wrapper.unmount()
  })
})
