import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppTabs from "./AppTabs.vue"

const OPTIONS = [
  { value: "favorites", label: "Favorites" },
  { value: "history", label: "History" },
]

describe("AppTabs", () => {
  it("marks the page shown, names each page after the row, and asks for another", async () => {
    const wrapper = mount(AppTabs, {
      global: { plugins: [Quasar] },
      props: { modelValue: "favorites", options: OPTIONS },
      attrs: { "data-testid": "places" },
    })

    expect(wrapper.get('[data-testid="places-favorites"]').attributes("aria-pressed")).toBe("true")
    expect(wrapper.get('[data-testid="places-history"]').attributes("aria-pressed")).toBe("false")
    await wrapper.get('[data-testid="places-history"]').trigger("click")
    expect(wrapper.emitted("update:modelValue")).toEqual([["history"]])
  })
})
