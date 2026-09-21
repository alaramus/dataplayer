import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import AppFormControl from "./AppFormControl.vue"
import { formLayoutKey } from "./formLayout"

describe("AppFormControl", () => {
  it("stands in the control column only inside a form", () => {
    const inForm = mount(AppFormControl, {
      global: { provide: { [formLayoutKey as symbol]: true } },
      slots: { default: "public / demo_lab" },
    })
    expect(inForm.classes()).toContain("app-form-control--form")
    expect(inForm.text()).toBe("public / demo_lab")
    const outside = mount(AppFormControl, { slots: { default: "public" } })
    expect(outside.classes()).not.toContain("app-form-control--form")
  })
})
