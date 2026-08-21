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

    expect(wrapper.findAll("[data-testid^='field-']")).toHaveLength(4)
  })

  // Quasar forwards undeclared attributes onto the <input> itself rather than
  // the field root, so data-testid addresses the input directly.
  it("renders a secret field as a password input", () => {
    const wrapper = mountFields()

    const input = wrapper.find("[data-testid='field-password']")
    expect(input.attributes("type")).toBe("password")
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
})
