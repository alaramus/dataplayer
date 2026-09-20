import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppBanner from "./AppBanner.vue"
import { bannerLook, type Tone } from "./tokens"

function mountBanner(tone: Tone) {
  return mount(AppBanner, {
    global: { plugins: [Quasar] },
    props: { tone },
    slots: { default: "Something happened" },
    attrs: { "data-testid": "the-banner" },
  })
}

describe("AppBanner", () => {
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

  it("shows the message it was given", () => {
    expect(mountBanner("error").text()).toContain("Something happened")
  })
})
