import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppCopyButton from "./AppCopyButton.vue"

describe("AppCopyButton", () => {
  it("renders the standard copy icon and keeps the test id", () => {
    const wrapper = mount(AppCopyButton, {
      global: { plugins: [Quasar] },
      attrs: { "data-testid": "copy-value" },
    })

    expect(wrapper.get("button").attributes("data-testid")).toBe("copy-value")
    expect(wrapper.get("button").attributes("aria-label")).toBe("Copy")
    expect(wrapper.get(".q-icon").text()).toBe("content_copy")
  })

  it("stands at a line's height inside text or a cell when compact", () => {
    const plain = mount(AppCopyButton, { global: { plugins: [Quasar] } })
    const compact = mount(AppCopyButton, { global: { plugins: [Quasar] }, props: { compact: true } })

    expect(plain.get("button").classes()).not.toContain("app-icon-button__compact")
    expect(compact.get("button").classes()).toContain("app-icon-button__compact")
  })
})
