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

  /**
   * U04: four commands on the narrow rails dropped their label to fit and
   * became buttons with no name at all. A tooltip beside one names nothing:
   * the label is kept and spoken instead of drawn.
   */
  it("keeps the label as its name when only the icon is drawn", () => {
    const wrapper = mount(AppButton, {
      global: { plugins: [Quasar] },
      props: { label: "Dashboards", icon: "dashboard", iconOnly: true },
    })

    expect(wrapper.get("button").text()).not.toContain("Dashboards")
    expect(wrapper.get("button").attributes("aria-label")).toBe("Dashboards")
  })

  it("leaves a drawn label to name the button itself", () => {
    // Both a visible label and an aria-label is one name too many: a reader
    // that announces the second ignores the first.
    expect(mountButton("primary").get("button").attributes("aria-label")).toBeUndefined()
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
