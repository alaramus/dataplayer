import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppNumberInput from "./AppNumberInput.vue"

function mountInput(props: Record<string, unknown> = {}) {
  return mount(AppNumberInput, {
    global: { plugins: [Quasar] },
    props: { modelValue: 5432, label: "Port", ...props },
    attrs: { "data-testid": "field-port" },
  })
}

describe("AppNumberInput", () => {
  it("keeps the test id on the input element", () => {
    expect(mountInput().get("input").attributes("data-testid")).toBe("field-port")
  })

  it("says a field is wrong to a screen reader and not only in colour", () => {
    expect(mountInput({ error: "Too low" }).get("input").attributes("aria-invalid")).toBe(
      "true"
    )
    expect(mountInput().get("input").attributes("aria-invalid")).toBeUndefined()
  })

  it("reports a number, not the text that was typed", async () => {
    const wrapper = mountInput()

    await wrapper.get("input").setValue("6543")

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([6543])
  })

  // A port nobody filled in is missing, not zero.
  it("reports an emptied field as null", async () => {
    const wrapper = mountInput()

    await wrapper.get("input").setValue("")

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([null])
  })

  it("shows the error message", () => {
    expect(mountInput({ error: "Out of range" }).text()).toContain("Out of range")
  })

  it("keeps a companion action in the field's marginal area", () => {
    const wrapper = mount(AppNumberInput, {
      global: { plugins: [Quasar] },
      props: { modelValue: 5432, label: "Port" },
      slots: { after: '<button data-testid="field-action">Reset</button>' },
    })

    expect(wrapper.get('[data-testid="field-action"]').element.parentElement?.classList).toContain(
      "q-field__after"
    )
  })
})
