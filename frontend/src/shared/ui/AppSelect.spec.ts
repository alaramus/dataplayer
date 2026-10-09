import { flushPromises, mount } from "@vue/test-utils"
import { QSelect, Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"

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

  it("uses the neutral selection colour outside forms too", () => {
    const select = mountSelect({ options: LABELLED, compact: true }).getComponent(QSelect)
    expect(select.props("color")).toBe("dp-field-focus")
  })

  it("leaves plain string options alone", () => {
    const select = mountSelect({ options: ["disable", "prefer"] }).getComponent(QSelect)

    expect(select.props("optionValue")).toBeUndefined()
    expect(select.props("emitValue")).toBe(false)
  })

  it("passes over group headings as it does over a choice not yet available", () => {
    const select = mountSelect({
      options: [
        { label: "Anthropic", value: "provider:anthropic", group: true },
        { label: "Claude", value: "claude", description: "API key required" },
        { label: "GPT", value: "gpt", disable: true },
      ],
    }).getComponent(QSelect)

    const disable = select.props("optionDisable") as (option: {
      group?: boolean
      disable?: boolean
    }) => boolean
    expect(disable({ group: true })).toBe(true)
    expect(disable({ disable: true })).toBe(true)
    expect(disable({})).toBe(false)
  })

  it("shows the selected string option", () => {
    expect(mountSelect({ modelValue: "prefer", options: ["disable", "prefer"] }).text()).toContain(
      "prefer"
    )
  })

  it("names a toolbar field beside it, or for a reader alone when its label is hidden", () => {
    const shown = mountSelect({ options: LABELLED, compact: true, label: "Kind" })
    expect(shown.find(".app-select__inline-label").text()).toBe("Kind")

    const hidden = mountSelect({ options: LABELLED, compact: true, label: "Kind", labelHidden: true })
    expect(hidden.find(".app-select__inline-label").exists()).toBe(false)
    expect(hidden.get('[role="combobox"]').attributes("aria-label")).toBe("Kind")
  })

  it("shows the label of the selected labelled option", () => {
    expect(mountSelect({ modelValue: "file", options: LABELLED }).text()).toContain("Files")
  })

  // Seven schemas ticked in the catalog's toolbar grew the field into four
  // rows of chips, which pushed out of the panel and over the tabs above it.
  it("counts several choices in one line while it stands in a toolbar", () => {
    const wrapper = mountSelect({
      modelValue: ["public", "sales", "pg_catalog"],
      options: ["public", "sales", "pg_catalog"],
      multiple: true,
      compact: true,
      summaryNoun: "Schemas",
    })

    // Not "public +2": naming one of them makes it look chosen in a way the
    // others are not, and which one leads is the order they were ticked in.
    expect(wrapper.get(".app-select__summary").text()).toBe("3 schemas")
  })

  it("counts without a noun where the caller has not given one", () => {
    const wrapper = mountSelect({
      modelValue: ["a", "b"],
      options: ["a", "b"],
      multiple: true,
      compact: true,
    })

    expect(wrapper.get(".app-select__summary").text()).toBe("2 selected")
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

  // A toolbar is one line: the message row and the error icon each grew the
  // box, so both stay off here. Only the frame reddens, while the message
  // stays in the alert for a reader.
  it("keeps a toolbar field's box in error", () => {
    const wrapper = mountSelect({ options: ["a"], compact: true, error: "Pick one" })
    const field = wrapper.getComponent(QSelect)

    expect(field.props("noErrorIcon")).toBe(true)
    expect(field.props("hideBottomSpace")).toBe(true)
    expect(wrapper.find(".q-field--error").exists()).toBe(true)
    expect(wrapper.get('[role="alert"]').text()).toBe("Pick one")
  })

  it("keeps Quasar's error icon and message space outside toolbars", () => {
    const field = mountSelect({ options: ["a"], error: "Pick one" }).getComponent(QSelect)

    expect(field.props("noErrorIcon")).toBeFalsy()
    expect(field.props("hideBottomSpace")).toBeFalsy()
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

  it("draws the state of the one chosen option after its name", () => {
    const options = [
      { label: "Claude", value: "claude", description: "API key set", stateIcon: "key", stateActive: true },
      { label: "GPT", value: "gpt", description: "API key required", stateIcon: "key_off" },
    ]
    const chosen = mountSelect({ modelValue: "claude", options })
    expect(chosen.get(".app-select__chosen-label").text()).toBe("Claude")
    expect(chosen.get(".app-select__state").text()).toBe("key")
    expect(chosen.get(".app-select__state").classes()).toContain("app-select__state--on")

    const unset = mountSelect({ modelValue: "gpt", options })
    expect(unset.get(".app-select__state").text()).toBe("key_off")
    expect(unset.get(".app-select__state").classes()).not.toContain("app-select__state--on")
  })

  it("styles the state it draws when the options arrive after the field", async () => {
    // The field drew its own <span> first; patched in place, the chosen name
    // lost this component's scope attribute and with it the gap by the key.
    const wrapper = mountSelect({ modelValue: "claude", options: [] })
    await wrapper.setProps({
      options: [{ label: "Claude", value: "claude", stateIcon: "key", stateActive: true }],
    })

    const scope = Object.keys(wrapper.attributes()).find((name) => name.startsWith("data-v-"))
    expect(scope).toBeDefined()
    expect(wrapper.get(".app-select__chosen").attributes()).toHaveProperty(scope ?? "")
  })

  // The click never reaches the field's own handler, so without an explicit
  // close the popup stays open over whatever the action shows.
  it("closes the popup when an option action takes over", async () => {
    const option = {
      label: "Claude",
      value: "claude",
      actionIcon: "key",
      actionLabel: "Manage Anthropic API key",
    }
    const wrapper = mount(AppSelect, {
      attachTo: document.body,
      global: { plugins: [Quasar] },
      props: { modelValue: null, options: [option] },
    })
    const field = wrapper.getComponent(QSelect).vm as unknown as {
      showPopup: () => void
      hidePopup: () => void
    }
    const hide = vi.spyOn(field, "hidePopup")
    field.showPopup()

    // The popup positions itself on an animation frame, which promises alone
    // do not flush.
    await vi.waitFor(() => {
      expect(document.body.querySelector('button[aria-label="Manage Anthropic API key"]')).not.toBeNull()
    })
    const action = document.body.querySelector('button[aria-label="Manage Anthropic API key"]')
    action?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    await flushPromises()

    expect(wrapper.emitted("optionAction")).toEqual([[option]])
    expect(hide).toHaveBeenCalled()
    wrapper.unmount()
  })

  it("never takes a heading from the keyboard", async () => {
    const wrapper = mount(AppSelect, {
      attachTo: document.body,
      global: { plugins: [Quasar] },
      props: {
        modelValue: null,
        options: [
          { label: "Anthropic", value: "provider:anthropic", group: true, actionIcon: "key", actionLabel: "Manage Anthropic API key" },
          { label: "Claude", value: "claude" },
        ],
      },
    })
    const field = wrapper.getComponent(QSelect).vm as unknown as { showPopup: () => void }
    field.showPopup()
    await vi.waitFor(() => {
      expect(document.body.querySelector('[role="option"]')).not.toBeNull()
    })
    // Drawn as a heading, not as an option a reader would be offered.
    expect(document.body.querySelectorAll('[role="option"]')).toHaveLength(1)

    const combobox = wrapper.get('[role="combobox"]')
    await combobox.trigger("keydown", { key: "ArrowDown", keyCode: 40 })
    await combobox.trigger("keydown", { key: "Enter", keyCode: 13 })
    await flushPromises()

    expect(wrapper.emitted("update:modelValue")).toEqual([["claude"]])
    wrapper.unmount()
  })

  // A heading carries its own button but is never a choice: pressing the
  // row itself selects nothing, while the button still takes over.
  it("keeps a heading action pressable without making the heading a choice", async () => {
    const heading = {
      label: "Anthropic",
      value: "provider:anthropic",
      group: true,
      actionIcon: "key",
      actionLabel: "Manage Anthropic API key",
    }
    const wrapper = mount(AppSelect, {
      attachTo: document.body,
      global: { plugins: [Quasar] },
      props: { modelValue: null, options: [heading] },
    })
    const field = wrapper.getComponent(QSelect).vm as unknown as {
      showPopup: () => void
      hidePopup: () => void
    }
    const hide = vi.spyOn(field, "hidePopup")
    field.showPopup()

    await vi.waitFor(() => {
      expect(document.body.querySelector('button[aria-label="Manage Anthropic API key"]')).not.toBeNull()
    })
    // Disabled to QSelect, not on the row: an aria-disabled row takes the
    // button with it for a reader and for Playwright.
    expect(document.body.querySelector(".q-item.disabled")).toBeNull()
    expect(document.body.querySelector('.q-item[aria-disabled="true"]')).toBeNull()

    const row = document.body.querySelector(".q-item")
    row?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    await flushPromises()
    expect(wrapper.emitted("update:modelValue")).toBeUndefined()

    const action = document.body.querySelector('button[aria-label="Manage Anthropic API key"]')
    action?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    await flushPromises()

    expect(wrapper.emitted("optionAction")).toEqual([[heading]])
    expect(wrapper.emitted("update:modelValue")).toBeUndefined()
    expect(hide).toHaveBeenCalled()
    wrapper.unmount()
  })
})
