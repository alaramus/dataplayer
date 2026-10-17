import { mount } from "@vue/test-utils"
import { QFile, Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppFileInput from "./AppFileInput.vue"

function file(name: string): File {
  return new File(["x"], name)
}

function mountInput(props: Record<string, unknown>) {
  return mount(AppFileInput, {
    global: { plugins: [Quasar] },
    props: { modelValue: [], ...props },
  })
}

describe("AppFileInput", () => {
  // Empty, Quasar drew a blank input that read as a text field.
  it("says a click picks a file while nothing is chosen", () => {
    expect(mountInput({ modelValue: null }).getComponent(QFile).props("displayValue")).toBe("Choose a file")
    expect(mountInput({ modelValue: [], multiple: true }).getComponent(QFile).props("displayValue")).toBe("Choose files")
    expect(mountInput({ modelValue: file("a.csv") }).getComponent(QFile).props("displayValue")).toBeUndefined()
  })

  // The upload form lists what was chosen with sizes and a way to take one
  // out; the field repeating the same names in one line said it twice.
  it("stays empty when the screen lists the choice itself", () => {
    const wrapper = mountInput({ modelValue: [file("a.csv")], multiple: true, listed: true })

    expect(wrapper.getComponent(QFile).props("modelValue")).toBeNull()
  })

  it("adds what was just picked to what the screen already holds", () => {
    const held = file("a.csv")
    const picked = file("b.csv")
    const wrapper = mountInput({ modelValue: [held], multiple: true, append: true, listed: true })

    wrapper.getComponent(QFile).vm.$emit("update:modelValue", [picked])

    expect(wrapper.emitted("update:modelValue")).toEqual([[[held, picked]]])
  })

  it("replaces the set with a pick when it does not add to it", () => {
    const picked = file("b.csv")
    const wrapper = mountInput({ modelValue: [file("a.csv")], listed: true })

    wrapper.getComponent(QFile).vm.$emit("update:modelValue", picked)

    expect(wrapper.emitted("update:modelValue")).toEqual([[[picked]]])
  })

  it("shows the choice in the field when nothing lists it below", () => {
    const held = [file("a.csv")]
    const wrapper = mountInput({ modelValue: held, multiple: true })

    expect(wrapper.getComponent(QFile).props("modelValue")).toEqual(held)
  })
})
