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

  it("reports what the user typed", async () => {
    const wrapper = mountInput()

    await wrapper.get("input").setValue("db.internal")

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["db.internal"])
  })
})
