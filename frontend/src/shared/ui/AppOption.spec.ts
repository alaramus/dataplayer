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
  // A heading is never chosen, so with a working button of its own it takes
  // neither the dim nor the forbidden arrow — only its button points. The
  // cursor itself is Quasar CSS, which unit tests never load; the classes
  // below are what those rules hang on.
  it("marks a heading whose button is switched on", () => {
    const headed = mountOption({
      label: "Anthropic",
      value: "provider:anthropic",
      group: true,
      actionIcon: "key",
      actionLabel: "Manage Anthropic API key",
      actionActive: true,
    })
    expect(headed.get(".q-item").classes()).toContain("app-option--live-heading")
    expect(headed.find(".app-option__action").exists()).toBe(true)

    const plain = mountOption({ label: "Recent", value: "group:recent", group: true })
    expect(plain.get(".q-item").classes()).not.toContain("app-option--live-heading")

    // Without a key the heading stays dimmed like any other unavailable
    // choice, so its mark is the colour of the other missing ones.
    const missing = mountOption({
      label: "Anthropic",
      value: "provider:anthropic",
      group: true,
      actionIcon: "key_off",
      actionLabel: "Manage Anthropic API key",
    })
    expect(missing.get(".q-item").classes()).not.toContain("app-option--live-heading")
    expect(missing.find(".app-option__action").exists()).toBe(true)
  })

  it("marks the working button of an unavailable choice", () => {
    const wrapper = mountOption({
      label: "Choose with Jev",
      value: "auto:anthropic",
      disable: true,
      actionIcon: "key_off",
      actionLabel: "Manage TypeSafe (Jev) API key",
    })
    expect(wrapper.get(".q-item").classes()).not.toContain("app-option--live-heading")
    expect(wrapper.find(".app-option__action").exists()).toBe(true)
  })
})
