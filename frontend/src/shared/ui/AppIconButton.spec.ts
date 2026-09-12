import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppIconButton from "./AppIconButton.vue"

describe("AppIconButton", () => {
  it.each([false, true])("names the button before hover when disabled is %s", (disable) => {
    const wrapper = mount(AppIconButton, {
      global: { plugins: [Quasar] },
      props: { icon: "delete", tooltip: "Delete this row", disable },
    })

    expect(wrapper.get("button").attributes("aria-label")).toBe("Delete this row")
    wrapper.unmount()
  })

  it.each([false, true])("preserves an explicit accessible name when disabled is %s", (disable) => {
    const wrapper = mount(AppIconButton, {
      global: { plugins: [Quasar] },
      props: { icon: "delete", tooltip: "Select a row first", disable },
      attrs: { "aria-label": "Delete selected rows", "data-testid": "delete-rows" },
    })

    expect(wrapper.get("button").attributes("aria-label")).toBe("Delete selected rows")
    expect(wrapper.get("button").attributes("data-testid")).toBe("delete-rows")
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
    expect(wrapper.get("button").attributes("aria-label")).toBe("Switch to the dark theme")
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

  it("requires a tooltip, because an icon names nothing on its own", () => {
    // @ts-expect-error tooltip is not optional
    mount(AppIconButton, { global: { plugins: [Quasar] }, props: { icon: "delete" } })
  })
})
