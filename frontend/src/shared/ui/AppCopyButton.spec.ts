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
})
