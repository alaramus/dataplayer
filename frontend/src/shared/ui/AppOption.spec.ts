import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppOption from "./AppOption.vue"
import type { SelectOption } from "./AppSelect.vue"

function mountOption(option: SelectOption) {
  return mount(AppOption, {
    global: { plugins: [Quasar] },
    props: { option },
  })
}

describe("AppOption", () => {
  it("draws a heading's own button, with or without its key", () => {
    for (const actionIcon of ["key", "key_off"]) {
      const heading = mountOption({
        label: "Anthropic",
        value: "provider:anthropic",
        group: true,
        actionIcon,
        actionLabel: "Manage Anthropic API key",
        actionActive: actionIcon === "key",
      })
      expect(heading.find(".app-option__action").exists()).toBe(true)
    }
    const plain = mountOption({ label: "Recent", value: "group:recent", group: true })
    expect(plain.find(".app-option__action").exists()).toBe(false)
  })

  it("marks the working button of an unavailable choice", () => {
    const wrapper = mountOption({
      label: "Choose with Jev",
      value: "auto:anthropic",
      disable: true,
      actionIcon: "key_off",
      actionLabel: "Manage TypeSafe (Jev) API key",
    })
    expect(wrapper.find(".app-option__action").exists()).toBe(true)
  })
})
