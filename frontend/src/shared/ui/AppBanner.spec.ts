import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppBanner from "./AppBanner.vue"
import type { Tone } from "./tokens"

function mountBanner(tone: Tone) {
  return mount(AppBanner, {
    global: { plugins: [Quasar] },
    props: { tone },
    slots: { default: "Something happened" },
    attrs: { "data-testid": "the-banner" },
  })
}

describe("AppBanner", () => {
  // A Playwright scenario asserts bg-positive on the element it addresses by
  // test id, so the tone class and the test id must land on the same element.
  it("puts the tone class on the element carrying the test id", () => {
    const root = mountBanner("success").get("[data-testid='the-banner']")

    expect(root.classes()).toContain("bg-positive")
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
