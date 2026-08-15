import { describe, expect, it } from "vitest"

import { defaultValues, jsonSchemaToZod, schemaToFields } from "./jsonSchema"
import type { JsonSchema } from "./jsonSchema"

// Copied from the GET /api/v1/adapter-types/ response: the exact shape in which
// Pydantic emits the PostgresOptions schema.
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
  it("keeps the order of properties", () => {
    const names = schemaToFields(POSTGRES_SCHEMA).map((field) => field.name)

    expect(names).toEqual(["host", "port", "database", "user", "password"])
  })

  it("uses the title as the label", () => {
    const [host] = schemaToFields(POSTGRES_SCHEMA)

    expect(host.label).toBe("Host")
  })

  it("falls back to the property name when there is no title", () => {
    const fields = schemaToFields({
      type: "object",
      properties: { plain_name: { type: "string" } },
    })

    expect(fields[0].label).toBe("plain_name")
  })

  it("marks password-formatted strings as secret", () => {
    const password = schemaToFields(POSTGRES_SCHEMA).find((f) => f.name === "password")

    expect(password?.kind).toBe("password")
  })

  it("maps integers to the number kind", () => {
    const port = schemaToFields(POSTGRES_SCHEMA).find((f) => f.name === "port")

    expect(port?.kind).toBe("number")
    expect(port?.defaultValue).toBe(5432)
  })

  it("maps booleans and enums", () => {
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

  it("marks required fields", () => {
    const fields = schemaToFields(POSTGRES_SCHEMA)

    expect(fields.find((f) => f.name === "host")?.required).toBe(true)
    expect(fields.find((f) => f.name === "port")?.required).toBe(false)
  })

  it("throws on an unsupported property type", () => {
    expect(() =>
      schemaToFields({
        type: "object",
        properties: { weird: { type: "array" } },
      })
    ).toThrow(/unsupported/i)
  })
})

describe("jsonSchemaToZod", () => {
  it("accepts valid values", () => {
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

  it("rejects a missing required field", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({ host: "localhost" })

    expect(result.success).toBe(false)
  })

  it("rejects an empty required string", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({
      host: "",
      database: "app",
      user: "postgres",
      password: "secret",
    })

    expect(result.success).toBe(false)
  })

  it("rejects a port outside the allowed range", () => {
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

  it("allows omitting an optional field", () => {
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
  it("uses schema defaults and leaves the rest blank", () => {
    expect(defaultValues(schemaToFields(POSTGRES_SCHEMA))).toEqual({
      host: "",
      port: 5432,
      database: "",
      user: "",
      password: "",
    })
  })

  it("defaults booleans to false", () => {
    const fields = schemaToFields({
      type: "object",
      properties: { ssl: { type: "boolean" } },
    })

    expect(defaultValues(fields)).toEqual({ ssl: false })
  })
})
