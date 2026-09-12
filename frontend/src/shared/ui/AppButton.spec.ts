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

  it("uses separate colours for filled danger and danger text", () => {
    expect(mountButton("danger").get("button").classes()).toContain("bg-negative")
    expect(mountButton("danger-quiet").get("button").classes()).toContain("text-dp-action-danger")
  })

  // Action labels arrive from the server as sentences.
  it("does not uppercase the label", () => {
    expect(mountButton("primary").get("button").classes()).toContain("q-btn--no-uppercase")
  })

  // Which side an icon is on is part of what the button says: before the
  // label it names the action, after it points where the action goes. A
  // "Next" whose chevron sits on the left reads as walking backwards.
  it("puts an icon on the side it was asked for", () => {
    const before = mount(AppButton, {
      global: { plugins: [Quasar] },
      props: { label: "Back", icon: "chevron_left" },
    })
    const after = mount(AppButton, {
      global: { plugins: [Quasar] },
      props: { label: "Next", iconRight: "chevron_right" },
    })

    expect(before.get("button").text()).toBe("chevron_leftBack")
    expect(after.get("button").text()).toBe("Nextchevron_right")
  })

  // No test that a screen cannot pass color="purple": attributes fall through
  // by design, so nothing stops it. That compromise is recorded in the spec.
})
