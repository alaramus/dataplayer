import { mount } from "@vue/test-utils"
import { QSelect, Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppSelect from "./AppSelect.vue"

const LABELLED = [
  { label: "PostgreSQL", value: "postgres" },
  { label: "Files", value: "file" },
]

function mountSelect(props: Record<string, unknown>) {
  return mount(AppSelect, {
    global: { plugins: [Quasar] },
    props: { modelValue: null, options: [], ...props },
  })
}

describe("AppSelect", () => {
  // A call site used to repeat option-value, option-label, emit-value and
  // map-options whenever the options were objects, and omit all four when they
  // were strings. The shape of the options already says which is meant, so the
  // component reads it instead of the screen restating it.
  it("unpacks labelled options so the model holds the value, not the object", () => {
    const select = mountSelect({ options: LABELLED }).getComponent(QSelect)

    expect(select.props("optionValue")).toBe("value")
    expect(select.props("optionLabel")).toBe("label")
    expect(select.props("emitValue")).toBe(true)
    expect(select.props("mapOptions")).toBe(true)
  })

  it("leaves plain string options alone", () => {
    const select = mountSelect({ options: ["disable", "prefer"] }).getComponent(QSelect)

    expect(select.props("optionValue")).toBeUndefined()
    expect(select.props("emitValue")).toBe(false)
  })

  it("shows the selected string option", () => {
    expect(mountSelect({ modelValue: "prefer", options: ["disable", "prefer"] }).text()).toContain(
      "prefer"
    )
  })

  it("shows the label of the selected labelled option", () => {
    expect(mountSelect({ modelValue: "file", options: LABELLED }).text()).toContain("Files")
  })

  it("marks the field when it carries an error", () => {
    expect(mountSelect({ options: ["a"], error: "Pick one" }).find(".q-field--error").exists()).toBe(
      true
    )
  })

  it("treats an empty error string as no error", () => {
    expect(mountSelect({ options: ["a"], error: "" }).find(".q-field--error").exists()).toBe(false)
  })

  it("keeps a companion action in the field's marginal area", () => {
    const wrapper = mount(AppSelect, {
      global: { plugins: [Quasar] },
      props: { modelValue: "read", options: ["read"] },
      slots: { after: '<button data-testid="field-action">Share</button>' },
    })

    expect(wrapper.get('[data-testid="field-action"]').element.parentElement?.classList).toContain(
      "q-field__after"
    )
  })
})
