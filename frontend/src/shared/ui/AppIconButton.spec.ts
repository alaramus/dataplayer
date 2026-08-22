import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppIconButton from "./AppIconButton.vue"

describe("AppIconButton", () => {
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
