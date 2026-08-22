import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppButton from "./AppButton.vue"
import type { ButtonVariant } from "./tokens"

function mountButton(variant: ButtonVariant) {
  return mount(AppButton, {
    global: { plugins: [Quasar] },
    props: { variant, label: "Do it" },
    attrs: { "data-testid": "the-button" },
  })
}

describe("AppButton", () => {
  it("carries an undeclared attribute onto the button element", () => {
    const wrapper = mountButton("primary")

    expect(wrapper.get("button").attributes("data-testid")).toBe("the-button")
  })

  it("fills the main action and leaves the quiet one unfilled", () => {
    expect(mountButton("primary").get("button").classes()).toContain("bg-primary")
    expect(mountButton("quiet").get("button").classes()).not.toContain("bg-primary")
  })

  it("colours both destructive variants as negative", () => {
    expect(mountButton("danger").get("button").classes()).toContain("bg-negative")
    expect(mountButton("danger-quiet").get("button").classes()).toContain("text-negative")
  })

  // Action labels arrive from the server as sentences.
  it("does not uppercase the label", () => {
    expect(mountButton("primary").get("button").classes()).toContain("q-btn--no-uppercase")
  })

  it("does not let a screen choose the colour through a prop", () => {
    // @ts-expect-error the kit exposes meaning, not Quasar colours
    mount(AppButton, { global: { plugins: [Quasar] }, props: { color: "purple" } })
  })
})
