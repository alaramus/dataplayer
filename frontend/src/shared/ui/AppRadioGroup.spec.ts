import { mount } from "@vue/test-utils"
import { QRadio, Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppRadioGroup from "./AppRadioGroup.vue"
import { formLayoutKey } from "./formLayout"

const OPTIONS = [
  { label: "Current page", value: "page", description: "Rows 1–50" },
  { label: "All matching rows", value: "all", description: "Not offered here", disable: true },
  { label: "Selected rows", value: "selected" },
]

function mountGroup(form: boolean) {
  return mount(AppRadioGroup, {
    global: { plugins: [Quasar], provide: { [formLayoutKey as symbol]: form } },
    props: { modelValue: "page", options: OPTIONS, label: "Rows" },
    attrs: { "data-testid": "rows" },
  })
}

describe("AppRadioGroup", () => {
  it("names the group and each option, and describes an option by its line", () => {
    const wrapper = mountGroup(true)
    const group = wrapper.get('[role="radiogroup"]')
    expect(wrapper.get(`#${group.attributes("aria-labelledby") ?? ""}`).text()).toBe("Rows")

    const page = wrapper.get('[data-testid="rows-page"]')
    expect(page.attributes("role")).toBe("radio")
    expect(page.attributes("aria-label")).toBe("Current page")
    expect(page.attributes("aria-checked")).toBe("true")
    expect(wrapper.get(`#${page.attributes("aria-describedby") ?? ""}`).text()).toBe("Rows 1–50")
    expect(wrapper.get('[data-testid="rows-selected"]').attributes("aria-describedby")).toBeUndefined()
  })

  it("reports the chosen value and nothing for a disabled or repeated choice", async () => {
    const wrapper = mountGroup(false)
    await wrapper.get('[data-testid="rows-selected"]').trigger("click")
    await wrapper.get('[data-testid="rows-all"]').trigger("click")
    await wrapper.get('[data-testid="rows-page"]').trigger("click")
    expect(wrapper.emitted("update:modelValue")).toEqual([["selected"]])
  })

  it("marks a choice neutrally in a form and keeps Quasar's defaults outside one", () => {
    const inForm = mountGroup(true).getComponent(QRadio)
    expect(inForm.props("dense")).toBe(true)
    expect(inForm.props("color")).toBe("dp-control-selected")
    const outside = mountGroup(false).getComponent(QRadio)
    expect(outside.props("dense")).toBe(false)
    expect(outside.props("color")).toBeUndefined()
  })
})
