import { describe, expect, it } from "vitest"

import { defaultValues, jsonSchemaToZod, schemaToFields } from "./jsonSchema"
import type { JsonSchema } from "./jsonSchema"

// Скопировано с ответа GET /api/v1/adapter-types/ — форма, в которой Pydantic
// отдаёт схему PostgresOptions.
const POSTGRES_SCHEMA: JsonSchema = {
  type: "object",
  title: "PostgresOptions",
  required: ["host", "database", "user", "password"],
  properties: {
    host: { type: "string", title: "Host", minLength: 1 },
    port: { type: "integer", title: "Port", default: 5432, minimum: 1, maximum: 65535 },
    database: { type: "string", title: "Database", minLength: 1 },
    user: { type: "string", title: "User", minLength: 1 },
    password: { type: "string", title: "Password", format: "password", writeOnly: true },
  },
}

describe("schemaToFields", () => {
  it("сохраняет порядок свойств", () => {
    const names = schemaToFields(POSTGRES_SCHEMA).map((field) => field.name)

    expect(names).toEqual(["host", "port", "database", "user", "password"])
  })

  it("берёт метку из title", () => {
    const [host] = schemaToFields(POSTGRES_SCHEMA)

    expect(host.label).toBe("Host")
  })

  it("при отсутствии title подставляет имя свойства", () => {
    const fields = schemaToFields({
      type: "object",
      properties: { plain_name: { type: "string" } },
    })

    expect(fields[0].label).toBe("plain_name")
  })

  it("распознаёт секретное поле по format password", () => {
    const password = schemaToFields(POSTGRES_SCHEMA).find((f) => f.name === "password")

    expect(password?.kind).toBe("password")
  })

  it("отображает целые числа в числовой тип", () => {
    const port = schemaToFields(POSTGRES_SCHEMA).find((f) => f.name === "port")

    expect(port?.kind).toBe("number")
    expect(port?.defaultValue).toBe(5432)
  })

  it("отображает булевы значения и перечисления", () => {
    const fields = schemaToFields({
      type: "object",
      properties: {
        ssl: { type: "boolean", title: "SSL", default: false },
        mode: { type: "string", title: "Mode", enum: ["require", "disable"] },
      },
    })

    expect(fields[0].kind).toBe("boolean")
    expect(fields[1].kind).toBe("select")
    expect(fields[1].choices).toEqual(["require", "disable"])
  })

  it("помечает обязательные поля", () => {
    const fields = schemaToFields(POSTGRES_SCHEMA)

    expect(fields.find((f) => f.name === "host")?.required).toBe(true)
    expect(fields.find((f) => f.name === "port")?.required).toBe(false)
  })

  it("падает на неподдерживаемом типе свойства", () => {
    expect(() =>
      schemaToFields({
        type: "object",
        properties: { weird: { type: "array" } },
      })
    ).toThrow(/unsupported/i)
  })
})

describe("jsonSchemaToZod", () => {
  it("принимает корректные значения", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({
      host: "localhost",
      port: 5432,
      database: "app",
      user: "postgres",
      password: "secret",
    })

    expect(result.success).toBe(true)
  })

  it("отклоняет отсутствие обязательного поля", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({ host: "localhost" })

    expect(result.success).toBe(false)
  })

  it("отклоняет пустую обязательную строку", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({
      host: "",
      database: "app",
      user: "postgres",
      password: "secret",
    })

    expect(result.success).toBe(false)
  })

  it("отклоняет порт вне допустимого диапазона", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({
      host: "localhost",
      port: 70000,
      database: "app",
      user: "postgres",
      password: "secret",
    })

    expect(result.success).toBe(false)
  })

  it("разрешает опустить необязательное поле", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({
      host: "localhost",
      database: "app",
      user: "postgres",
      password: "secret",
    })

    expect(result.success).toBe(true)
  })
})

describe("defaultValues", () => {
  it("берёт значения по умолчанию из схемы, остальные оставляет пустыми", () => {
    expect(defaultValues(schemaToFields(POSTGRES_SCHEMA))).toEqual({
      host: "",
      port: 5432,
      database: "",
      user: "",
      password: "",
    })
  })

  it("для булевых полей подставляет false", () => {
    const fields = schemaToFields({
      type: "object",
      properties: { ssl: { type: "boolean" } },
    })

    expect(defaultValues(fields)).toEqual({ ssl: false })
  })
})
