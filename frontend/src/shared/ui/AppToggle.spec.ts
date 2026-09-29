import { mount } from "@vue/test-utils"
import { QToggle, Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppToggle from "./AppToggle.vue"
import { formLayoutKey } from "./formLayout"

describe("AppToggle", () => {
  it("uses the same neutral selected colour in a form and outside it", async () => {
    const inForm = mount(AppToggle, {
      global: { plugins: [Quasar], provide: { [formLayoutKey as symbol]: true } },
      props: { modelValue: false, label: "code" },
    })
    expect(inForm.getComponent(QToggle).props("color")).toBe("dp-control-selected")
    await inForm.get('[role="switch"]').trigger("click")
    expect(inForm.emitted("update:modelValue")).toEqual([[true]])
    const outside = mount(AppToggle, { global: { plugins: [Quasar] }, props: { modelValue: true } })
    expect(outside.getComponent(QToggle).props("color")).toBe("dp-control-selected")
  })

  // The full toggle keeps 12px of hit area left of its track and stands 40px
  // tall; dense, its track starts where the label above it starts (D187).
  it("is dense, so its track lines up with the text above it", () => {
    const toggle = mount(AppToggle, { global: { plugins: [Quasar] }, props: { modelValue: false } })
    expect(toggle.getComponent(QToggle).props("dense")).toBe(true)
  })
})
