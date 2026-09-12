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
