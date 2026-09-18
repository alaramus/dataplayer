import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppInput from "./AppInput.vue"

function mountInput(props: Record<string, unknown> = {}) {
  return mount(AppInput, {
    global: { plugins: [Quasar] },
    props: { modelValue: "localhost", label: "Host", ...props },
    attrs: { "data-testid": "field-host" },
  })
}

describe("AppInput", () => {
  // Asked of the field and not of the wrapper. A comment beside the root
  // element of a template makes the component a fragment in a development
  // build, and the wrapper then answers for the comment: every class it has
  // is gone, and the failure reads as the field having lost the class rather
  // than as the test having lost the field.
  it("keeps an empty autofill field's label above its value area", () => {
    const wrapper = mountInput({ modelValue: "", persistentLabel: true })
    expect(wrapper.get(".q-field").classes()).toContain("q-field--float")
    expect(wrapper.get("input").element.value).toBe("")
    wrapper.unmount()
  })

  it("forwards the new-password autocomplete hint to the password input", () => {
    const wrapper = mount(AppInput, {
      global: { plugins: [Quasar] },
      props: { modelValue: "", type: "password", label: "Password", persistentLabel: true },
      attrs: { autocomplete: "new-password" },
    })
    expect(wrapper.get("input").attributes("autocomplete")).toBe("new-password")
    wrapper.unmount()
  })

  // Quasar forwards an undeclared attribute onto the <input> rather than the
  // field root, and every existing test selector depends on that. Declaring
  // data-testid as a prop would have moved it.
  it("leaves the test id on the input element itself", () => {
    expect(mountInput().get("input").attributes("data-testid")).toBe("field-host")
  })

  // A growing box is also the one without a corner grip: Quasar turns both off
  // through this class, and a unit test cannot read the stylesheet that does.
  it("marks a growing textarea so it follows its text", () => {
    const wrapper = mountInput({ type: "textarea", grow: true })
    expect(wrapper.get(".q-field").classes()).toContain("q-textarea--autogrow")
    wrapper.unmount()
  })

  it("renders a secret as a password input", () => {
    expect(mountInput({ type: "password" }).get("input").attributes("type")).toBe("password")
  })

  // The caller holds a string, not the union QInput happens to report.
  it("reports an empty field as an empty string rather than null", async () => {
    const wrapper = mountInput()

    await wrapper.get("input").setValue("")

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([""])
  })

  it("treats an empty error string as no error", () => {
    expect(mountInput({ error: "" }).find(".q-field--error").exists()).toBe(false)
    expect(mountInput({ error: "Required" }).find(".q-field--error").exists()).toBe(true)
  })

  it("shows the error message", () => {
    expect(mountInput({ error: "Required" }).text()).toContain("Required")
  })

  it("links a compact field to its error until corrected", async () => {
    const wrapper = mountInput({ compact: true, error: "Enter a value" })
    const input = wrapper.get("input")
    const message = wrapper.get('[role="alert"]')
    expect(input.attributes("aria-describedby")).toBe(message.attributes("id"))
    expect(message.text()).toBe("Enter a value")

    await wrapper.setProps({ error: "" })
    expect(input.attributes("aria-describedby")).toBeUndefined()
    expect(input.attributes("aria-invalid")).toBeUndefined()
    wrapper.unmount()
  })

  it("preserves an existing description alongside the error", () => {
    const wrapper = mount(AppInput, {
      global: { plugins: [Quasar] },
      props: { modelValue: "", error: "Required" },
      attrs: { "aria-describedby": "value-help" },
    })
    expect(wrapper.get("input").attributes("aria-describedby")).toBe(
      `value-help ${wrapper.get('[role="alert"]').attributes("id")}`
    )
    wrapper.unmount()
  })

  it("says a field is wrong to a screen reader and not only in colour", () => {
    expect(mountInput({ error: "Required" }).get("input").attributes("aria-invalid")).toBe(
      "true"
    )
    // Absent rather than "false": a field nobody has objected to is not a
    // field announcing that it is fine.
    expect(mountInput().get("input").attributes("aria-invalid")).toBeUndefined()
  })

  it("keeps a companion action in the field's marginal area", () => {
    const wrapper = mount(AppInput, {
      global: { plugins: [Quasar] },
      props: { modelValue: "localhost", label: "Host" },
      slots: { after: '<button data-testid="field-action">Copy</button>' },
    })

    expect(wrapper.get('[data-testid="field-action"]').element.parentElement?.classList).toContain(
      "q-field__after"
    )
  })

  it("reports what the user typed", async () => {
    const wrapper = mountInput()

    await wrapper.get("input").setValue("db.internal")

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["db.internal"])
  })
})
