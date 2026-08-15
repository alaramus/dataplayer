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
  it("отрисовывает по одному элементу управления на поле", () => {
    const wrapper = mountFields()

    expect(wrapper.findAll("[data-testid^='field-']")).toHaveLength(4)
  })

  // Quasar пробрасывает неописанные атрибуты на сам <input>, а не на корень
  // поля, поэтому data-testid адресует элемент ввода напрямую.
  it("отрисовывает секретное поле как поле пароля", () => {
    const wrapper = mountFields()

    const input = wrapper.find("[data-testid='field-password']")
    expect(input.attributes("type")).toBe("password")
  })

  it("отрисовывает булево поле переключателем", () => {
    const wrapper = mountFields()

    expect(wrapper.find("[data-testid='field-ssl'] .q-toggle__inner").exists()).toBe(true)
  })

  it("показывает текст ошибки поля", () => {
    const wrapper = mountFields({ host: "Host is required" })

    expect(wrapper.text()).toContain("Host is required")
  })

  it("сообщает об изменении значения", async () => {
    const wrapper = mountFields()

    await wrapper.find("[data-testid='field-host']").setValue("db.internal")

    const emitted = wrapper.emitted("update:modelValue")
    expect(emitted).toBeTruthy()
    expect((emitted!.at(-1)![0] as Record<string, unknown>).host).toBe("db.internal")
  })

  it("приводит значение числового поля к числу", async () => {
    const wrapper = mountFields()

    await wrapper.find("[data-testid='field-port']").setValue("6543")

    const emitted = wrapper.emitted("update:modelValue")
    expect((emitted!.at(-1)![0] as Record<string, unknown>).port).toBe(6543)
  })
})
