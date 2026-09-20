import { mount } from "@vue/test-utils"
import { QCheckbox, Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppCheckbox from "./AppCheckbox.vue"
import { formLayoutKey } from "./formLayout"

describe("form checkbox", () => {
  it("keeps its label, keyboard state and boolean value contract in a form", async () => {
    const wrapper = mount(AppCheckbox, {
      global: { plugins: [Quasar], provide: { [formLayoutKey as symbol]: true } },
      props: { modelValue: false, label: "Unique", indeterminate: true },
    })
    expect(wrapper.get('[role="checkbox"]').attributes("aria-checked")).toBe("mixed")
    expect(wrapper.text()).toContain("Unique")
    expect(wrapper.getComponent(QCheckbox).props("dense")).toBe(true)
    expect(wrapper.getComponent(QCheckbox).props("color")).toBe("dp-control-selected")
    await wrapper.get('[role="checkbox"]').trigger("click")
    expect(wrapper.emitted("update:modelValue")).toEqual([[true]])
    const disabled = mount(AppCheckbox, {
      global: { plugins: [Quasar] },
      props: { modelValue: false }, attrs: { disable: true },
    })
    await disabled.get('[role="checkbox"]').trigger("click")
    expect(disabled.emitted("update:modelValue")).toBeUndefined()
  })

  it("retains the existing defaults outside forms", () => {
    const wrapper = mount(AppCheckbox, {
      global: { plugins: [Quasar] }, props: { modelValue: true },
    })
    expect(wrapper.getComponent(QCheckbox).props("dense")).toBe(false)
    expect(wrapper.getComponent(QCheckbox).props("color")).toBeUndefined()
  })
})
