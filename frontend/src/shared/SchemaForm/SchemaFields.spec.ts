import { flushPromises, mount } from "@vue/test-utils"
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
   * The connection form derives a tunnel's choices from the values it holds, so
   * it hands over a new array of fields with every keystroke. Resetting the eye
   * on the identity of that array hid the password the moment it was typed
   * into, which is not what the eye was asked for.
   */
  it("keeps a shown secret in plain text while it is typed into", async () => {
    const wrapper = mountFields()
    const typed = { host: "localhost", port: 5432, password: "correct-horse", ssl: false }
    await wrapper.setProps({ modelValue: typed })
    await wrapper.get("[data-testid='field-password-visibility']").trigger("click")
    expect(wrapper.get("[data-testid='field-password']").attributes("type")).toBe("text")

    // Every keystroke comes back as a recomputed list of fields.
    await wrapper.setProps({
      fields: schemaToFields(SCHEMA),
      modelValue: { ...typed, password: "correct-hors" },
    })
    expect(wrapper.get("[data-testid='field-password']").attributes("type")).toBe("text")

    // Emptying it, then typing again, does not hide it either: only the eye
    // decides, and it has not been pressed a second time.
    await wrapper.get("[data-testid='field-password']").setValue("")
    await wrapper.setProps({ modelValue: { ...typed, password: "" } })
    expect(wrapper.get("[data-testid='field-password']").attributes("type")).toBe("text")
    await wrapper.setProps({ modelValue: { ...typed, password: "c" } })
    expect(wrapper.get("[data-testid='field-password']").attributes("type")).toBe("text")
  })

  it("hides a shown secret when a different set of fields arrives", async () => {
    const wrapper = mountFields()
    await wrapper.setProps({
      modelValue: { host: "localhost", port: 5432, password: "correct-horse", ssl: false },
    })
    await wrapper.get("[data-testid='field-password-visibility']").trigger("click")
    expect(wrapper.get("[data-testid='field-password']").attributes("type")).toBe("text")

    // Another way of connecting is another set of secrets, even though the
    // field is still there.
    await wrapper.setProps({
      fields: schemaToFields({
        ...SCHEMA,
        properties: { ...SCHEMA.properties, user: { type: "string", title: "User" } },
      } as JsonSchema),
    })
    expect(wrapper.get("[data-testid='field-password']").attributes("type")).toBe("password")
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

  it("keeps a secret of several lines in a box, masked until its eye is pressed", async () => {
    // A kubeconfig is YAML: a one-line password field would drop its line breaks.
    const wrapper = mount(SchemaFields, {
      global: { plugins: [Quasar] },
      props: {
        fields: schemaToFields({
          type: "object",
          properties: {
            kubeconfig: {
              type: "string",
              title: "Kubeconfig",
              format: "password",
              "x-ui-multiline": true,
            },
          },
        }),
        modelValue: { kubeconfig: "apiVersion: v1\nkind: Config" },
        errors: {},
      },
    })

    const box = wrapper.get("[data-testid='field-kubeconfig']")
    expect(box.element.tagName).toBe("TEXTAREA")
    expect((box.element as HTMLTextAreaElement).value).toBe("apiVersion: v1\nkind: Config")
    expect(wrapper.find(".app-input--masked").exists()).toBe(true)
    await wrapper.get("[data-testid='field-kubeconfig-visibility']").trigger("click")
    expect(wrapper.find(".app-input--masked").exists()).toBe(false)
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

describe("SchemaFields on a shared line", () => {
  const SHARED: JsonSchema = {
    type: "object",
    properties: {
      host: { type: "string", title: "Host", row: "address" },
      port: { type: "integer", title: "Port", description: "The native port, 9042", row: "address" },
      user: { type: "string", title: "User", description: "Who signs in" },
    },
  } as JsonSchema

  it("puts the description of a field beside another behind an icon", () => {
    const wrapper = mount(SchemaFields, {
      global: { plugins: [Quasar] },
      props: { fields: schemaToFields(SHARED), modelValue: { host: "h", port: 9042, user: "u" }, errors: {} },
    })

    const tip = wrapper.get("[data-testid='field-port-tip']")
    expect(tip.attributes("aria-label")).toBe("The native port, 9042")
    expect(wrapper.text()).not.toContain("The native port, 9042")
    // A field alone on its line keeps its sentence under it.
    expect(wrapper.text()).toContain("Who signs in")
    expect(wrapper.find("[data-testid='field-user-tip']").exists()).toBe(false)
  })
})

describe("SchemaFields with a field read from a file", () => {
  const PEM = "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----\n"

  function mountKey(props: { secretsAreStored?: boolean; maxLength?: number } = {}) {
    return mount(SchemaFields, {
      global: { plugins: [Quasar] },
      props: {
        fields: schemaToFields({
          type: "object",
          properties: {
            host: { type: "string", title: "Host" },
            tls_client_key: {
              type: "string",
              title: "Client key",
              format: "password",
              "x-ui-multiline": true,
              "x-ui-file": ".pem,.key",
              maxLength: props.maxLength,
            },
          },
        }),
        modelValue: { host: "db", tls_client_key: "" },
        errors: {},
        secretsAreStored: props.secretsAreStored,
      },
    })
  }

  async function choose(wrapper: ReturnType<typeof mountKey>, file: File) {
    const input = wrapper.get("[data-testid='schema-fields-file']")
    // The button points the one picker at its field; the browser's dialog is
    // not there to open in a test, so the choice is handed to it directly.
    await wrapper.get("[data-testid='field-tls_client_key-from-file']").trigger("click")
    Object.defineProperty(input.element, "files", { value: [file], configurable: true })
    await input.trigger("change")
    await flushPromises()
  }

  it("offers a picker only on the field that says it can be read from a file", async () => {
    const wrapper = mountKey()

    expect(wrapper.find("[data-testid='field-host-from-file']").exists()).toBe(false)
    expect(wrapper.find("[data-testid='field-tls_client_key-from-file']").exists()).toBe(true)
    const input = wrapper.get<HTMLInputElement>("[data-testid='schema-fields-file']")
    await wrapper.get("[data-testid='field-tls_client_key-from-file']").trigger("click")
    expect(input.element.accept).toBe(".pem,.key")
  })

  it("puts the text of the chosen file in the field, as a paste would", async () => {
    const wrapper = mountKey({ secretsAreStored: true })

    await choose(wrapper, new File([PEM], "client.key"))

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([{ host: "db", tls_client_key: PEM }])
  })

  it("puts in a dropped file the same way", async () => {
    const wrapper = mountKey()
    const file = new File([PEM], "client.key")

    await wrapper.get("[data-testid='field-tls_client_key']").trigger("drop", {
      dataTransfer: { types: ["Files"], files: [file] },
    })
    await flushPromises()

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([{ host: "db", tls_client_key: PEM }])
  })

  it("says why a file was not read, under the field, and forgets it once the field changes", async () => {
    const wrapper = mountKey({ maxLength: 8 })

    await choose(wrapper, new File([PEM], "client.key"))

    expect(wrapper.emitted("update:modelValue")).toBeUndefined()
    expect(wrapper.get("[role='alert']").text()).toContain("Client key")

    await wrapper.get("[data-testid='field-tls_client_key']").setValue("x")
    expect(wrapper.find("[role='alert']").exists()).toBe(false)
  })
})
