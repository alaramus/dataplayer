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

  // Seven schemas ticked in the catalog's toolbar grew the field into four
  // rows of chips, which pushed out of the panel and over the tabs above it.
  it("says several choices in one line while it stands in a toolbar", () => {
    const wrapper = mountSelect({
      modelValue: ["public", "sales", "pg_catalog"],
      options: ["public", "sales", "pg_catalog"],
      multiple: true,
      compact: true,
    })

    expect(wrapper.get(".app-select__summary").text()).toBe("public +2")
  })

  it("names the one choice there is, with nothing to count", () => {
    const wrapper = mountSelect({
      modelValue: ["file"],
      options: LABELLED,
      multiple: true,
      compact: true,
    })

    expect(wrapper.get(".app-select__summary").text()).toBe("Files")
  })

  it("leaves a field in a form its chips, where the height is not spoken for", () => {
    const wrapper = mountSelect({
      modelValue: ["public", "sales"],
      options: ["public", "sales"],
      multiple: true,
    })

    expect(wrapper.find(".app-select__summary").exists()).toBe(false)
    expect(wrapper.text()).toContain("sales")
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
