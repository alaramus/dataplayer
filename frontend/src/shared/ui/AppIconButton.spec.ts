import { mount } from "@vue/test-utils"
import { QBtn, Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppIconButton from "./AppIconButton.vue"

/**
 * Disabled, the control is the wrapper: the button inside it is out of the tab
 * order and hidden from a reader, so that the pair is announced once and the
 * reason can be reached by keyboard rather than by hover alone (U14).
 */
const named = (wrapper: ReturnType<typeof mount>, disable: boolean) =>
  disable ? wrapper.get('[role="button"]') : wrapper.get("button")

describe("AppIconButton", () => {
  it.each([false, true])("names the button before hover when disabled is %s", (disable) => {
    const wrapper = mount(AppIconButton, {
      global: { plugins: [Quasar] },
      props: { icon: "delete", tooltip: "Delete this row", disable },
    })

    expect(named(wrapper, disable).attributes("aria-label")).toBe("Delete this row")
    wrapper.unmount()
  })

  it.each([false, true])("preserves an explicit accessible name when disabled is %s", (disable) => {
    const wrapper = mount(AppIconButton, {
      global: { plugins: [Quasar] },
      props: { icon: "delete", tooltip: "Select a row first", disable },
      attrs: { "aria-label": "Delete selected rows", "data-testid": "delete-rows" },
    })

    expect(named(wrapper, disable).attributes("aria-label")).toBe("Delete selected rows")
    // Still on the button, which is what a test and a screen address it by.
    expect(wrapper.get("button").attributes("data-testid")).toBe("delete-rows")
    wrapper.unmount()
  })

  it("puts a disabled command in the tab order, with its reason in its name", () => {
    const wrapper = mount(AppIconButton, {
      global: { plugins: [Quasar] },
      props: { icon: "delete", tooltip: "Delete — tick a row first", disable: true },
    })
    const control = wrapper.get('[role="button"]')

    expect(control.attributes("tabindex")).toBe("0")
    expect(control.attributes("aria-disabled")).toBe("true")
    expect(control.attributes("aria-label")).toBe("Delete — tick a row first")
    // Announced once: the button it wraps is still disabled and now silent.
    expect(wrapper.get("button").attributes("disabled")).toBeDefined()
    expect(wrapper.get("button").attributes("aria-hidden")).toBe("true")
    wrapper.unmount()
  })

  it("updates the name with the action and retains it while loading", async () => {
    const wrapper = mount(AppIconButton, {
      global: { plugins: [Quasar] },
      props: { icon: "light_mode", tooltip: "Switch to the light theme" },
    })

    await wrapper.setProps({ tooltip: "Switch to the dark theme", loading: true })
    expect(wrapper.get("button").attributes("aria-label")).toBe("Switch to the dark theme")
    await wrapper.setProps({ disable: true })
    expect(wrapper.get('[role="button"]').attributes("aria-label")).toBe(
      "Switch to the dark theme"
    )
    wrapper.unmount()
  })

  it("renders the icon and keeps the test id on the button", () => {
    const wrapper = mount(AppIconButton, {
      global: { plugins: [Quasar] },
      props: { icon: "delete", tooltip: "Delete" },
      attrs: { "data-testid": "remove" },
    })

    expect(wrapper.get("button").attributes("data-testid")).toBe("remove")
    expect(wrapper.get(".q-icon").text()).toBe("delete")
  })

  it("shows an active state without the caller choosing a colour", () => {
    const wrapper = mount(AppIconButton, {
      global: { plugins: [Quasar] },
      props: { icon: "key", tooltip: "Configured", active: true },
    })

    expect(wrapper.getComponent(QBtn).props("color")).toBe("positive")
  })

  it("requires a tooltip, because an icon names nothing on its own", () => {
    // @ts-expect-error tooltip is not optional
    mount(AppIconButton, { global: { plugins: [Quasar] }, props: { icon: "delete" } })
  })
})
