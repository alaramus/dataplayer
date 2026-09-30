import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import SchemaFields from "./SchemaFields.vue"
import { schemaToFields } from "./jsonSchema"
import type { JsonSchema } from "./jsonSchema"

const SCHEMA: JsonSchema = {
  type: "object",
  required: ["host", "password"],
  properties: {
    host: { type: "string", title: "Host" },
    port: { type: "integer", title: "Port", default: 5432 },
    password: { type: "string", title: "Password", format: "password" },
    ssl: { type: "boolean", title: "SSL" },
  },
}

function mountFields(errors: Record<string, string> = {}) {
  return mount(SchemaFields, {
    global: { plugins: [Quasar] },
    props: {
      fields: schemaToFields(SCHEMA),
      modelValue: { host: "localhost", port: 5432, password: "", ssl: false },
      errors,
    },
  })
}

describe("SchemaFields", () => {
  it("renders one control per field", () => {
    const wrapper = mountFields()

    const fields = wrapper
      .findAll("[data-testid^='field-']")
      .filter((control) => !control.attributes("data-testid")?.endsWith("-visibility"))
    expect(fields).toHaveLength(4)
  })

  // Quasar forwards undeclared attributes onto the <input> itself rather than
  // the field root, so data-testid addresses the input directly.
  it("renders a secret field as a password input", () => {
    const wrapper = mountFields()

    const input = wrapper.find("[data-testid='field-password']")
    expect(input.attributes("type")).toBe("password")
    expect(wrapper.find("[data-testid='field-password-visibility']").exists()).toBe(true)
    expect(wrapper.find("[role='button'][aria-disabled='true']").exists()).toBe(true)
  })

  it("lets the user show and hide an entered secret", async () => {
    const wrapper = mountFields()
    const input = wrapper.get("[data-testid='field-password']")
    await input.setValue("correct-horse")
    const update = wrapper.emitted("update:modelValue")!.at(-1)![0] as Record<string, unknown>
    expect(update.password).toBe("correct-horse")
    await wrapper.setProps({ modelValue: update })

    const visibility = wrapper.get("[data-testid='field-password-visibility']")
    expect(input.attributes("type")).toBe("password")
    expect(visibility.attributes("aria-label")).toBe("Show password")

    await visibility.trigger("click")
    expect(input.attributes("type")).toBe("text")
    expect(wrapper.get("[data-testid='field-password-visibility']").attributes("aria-label")).toBe(
      "Hide password"
    )

    await wrapper.get("[data-testid='field-password-visibility']").trigger("click")
    expect(input.attributes("type")).toBe("password")
  })

  /**
   * U03: with nothing said, Chrome read the pair of fields as a login form and
   * filled a saved address and password into a form for connecting to a
   * database, which then looked ready to test and save.
   */
  it("tells the browser these are not the credentials it keeps", () => {
    const wrapper = mountFields()

    expect(wrapper.find("[data-testid='field-host']").attributes("autocomplete")).toBe("off")
    expect(wrapper.find("[data-testid='field-port']").attributes("autocomplete")).toBe("off")
    expect(wrapper.find("[data-testid='field-password']").attributes("autocomplete")).toBe(
      "new-password"
    )
  })

  it("draws a value written on several lines as a box, with its example in it", () => {
    // What the user sees of a source's own instruction: the shape of a filled
    // field, inside the empty one, gone as soon as anything is typed.
    const wrapper = mount(SchemaFields, {
      global: { plugins: [Quasar] },
      props: {
        fields: schemaToFields({
          type: "object",
          properties: {
            value: {
              type: "string",
              title: "Fields",
              description: "One per line, written as field=value",
              examples: ["name=Ada\nborn=1815"],
              "x-ui-multiline": true,
            },
          },
        }),
        modelValue: { value: "" },
        errors: {},
      },
    })

    // Quasar forwards data-testid onto the native element itself, so the box
    // is the textarea rather than something inside it.
    const box = wrapper.get("textarea[data-testid='field-value']")
    expect(box.attributes("placeholder")).toBe("name=Ada\nborn=1815")
    expect(wrapper.text()).toContain("One per line, written as field=value")
  })

  it("renders a boolean field as a toggle", () => {
    const wrapper = mountFields()

    expect(wrapper.find("[data-testid='field-ssl'] .q-toggle__inner").exists()).toBe(true)
  })

  it("shows the error text for a field", () => {
    const wrapper = mountFields({ host: "Host is required" })

    expect(wrapper.text()).toContain("Host is required")
  })

  it("emits an update when a value changes", async () => {
    const wrapper = mountFields()

    await wrapper.find("[data-testid='field-host']").setValue("db.internal")

    const emitted = wrapper.emitted("update:modelValue")
    expect(emitted).toBeTruthy()
    expect((emitted!.at(-1)![0] as Record<string, unknown>).host).toBe("db.internal")
  })

  it("coerces a numeric field value to a number", async () => {
    const wrapper = mountFields()

    await wrapper.find("[data-testid='field-port']").setValue("6543")

    const emitted = wrapper.emitted("update:modelValue")
    expect((emitted!.at(-1)![0] as Record<string, unknown>).port).toBe(6543)
  })

  it("draws a field whose purpose the screen knows with the screen's own slot", async () => {
    // The server key of an SSH connection is compared and trusted, not typed
    // (D145); the form knows only that a slot is offered for its purpose.
    const wrapper = mount(SchemaFields, {
      global: { plugins: [Quasar] },
      props: {
        fields: [
          { name: "host_key", label: "Server key", kind: "text", required: false, group: "general", purpose: "ssh-host-key" },
        ],
        modelValue: { host_key: "" },
        errors: {},
      },
      slots: {
        "field-ssh-host-key": `<template #field-ssh-host-key="{ value, update }">
          <button data-testid="trust" @click="update('ssh-ed25519 AAAA')">{{ value === "" ? "none" : value }}</button>
        </template>`,
      },
    })

    expect(wrapper.find("[data-testid='field-host_key']").exists()).toBe(false)
    expect(wrapper.get("[data-testid='trust']").text()).toBe("none")
    await wrapper.get("[data-testid='trust']").trigger("click")
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([{ host_key: "ssh-ed25519 AAAA" }])
  })
})
