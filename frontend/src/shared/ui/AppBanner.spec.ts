import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppBanner from "./AppBanner.vue"
import { bannerLook, type Tone } from "./tokens"
import { formLayoutKey } from "./formLayout"

function mountBanner(tone: Tone) {
  return mount(AppBanner, {
    global: { plugins: [Quasar] },
    props: { tone },
    slots: { default: "Something happened" },
    attrs: { "data-testid": "the-banner" },
  })
}

describe("AppBanner", () => {
  it("keeps the status and recovery action in a compact form", async () => {
    const wrapper = mount(AppBanner, {
      global: { plugins: [Quasar], provide: { [formLayoutKey as symbol]: true } },
      props: { tone: "warning" },
      slots: { default: "Some rows block this change", action: "Correct the values first" },
    })
    // In a form the words are the form's and the icon carries the tone; an
    // error keeps its words red, as a field's error does (D187).
    expect(wrapper.classes().some((name) => name.startsWith("dp-tone-"))).toBe(false)
    expect(wrapper.get(".q-icon").classes()).toContain("dp-tone-text-warning")
    expect(wrapper.text()).toContain("Some rows block this change")
    expect(wrapper.text()).toContain("Correct the values first")
    expect(wrapper.get(".q-icon").text()).toBe(bannerLook("warning").icon)
    await wrapper.setProps({ tone: "error" })
    expect(wrapper.classes()).toContain("dp-tone-text-error")
  })
  // A screen addresses the banner by its test id and the theme paints it by its
  // tone class, so the two must land on the same element.
  it("puts the tone class on the element carrying the test id", () => {
    const root = mountBanner("success").get("[data-testid='the-banner']")

    expect(root.classes()).toContain(bannerLook("success").classes)
  })

  it("gives every tone its own icon", () => {
    const icons = (["error", "success", "warning", "info"] as const).map((tone) =>
      mountBanner(tone).get(".q-icon").text()
    )

    expect(new Set(icons).size).toBe(4)
  })

  // A filled red ground left no colour for what stands on it: a countdown and
  // a Roll back were drawn on it at 1.6:1 (D187).
  it("washes every tone and colours only the icon", () => {
    for (const tone of ["error", "success", "warning", "info"] as const) {
      const banner = mountBanner(tone)
      expect(banner.classes()).toContain(`dp-tone-wash-${tone}`)
      expect(banner.get(".q-icon").classes()).toContain(`dp-tone-text-${tone}`)
    }
  })

  it("shows the message it was given", () => {
    expect(mountBanner("error").text()).toContain("Something happened")
  })
})
