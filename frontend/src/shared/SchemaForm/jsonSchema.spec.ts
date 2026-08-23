import { describe, expect, it } from "vitest"

import { at, first, keyed } from "@/shared/testing/collections"

import {
  defaultValues,
  fieldGroups,
  fieldRows,
  fieldsToZod,
  jsonSchemaToZod,
  readSchema,
  schemaToFields,
} from "./jsonSchema"
import type { JsonSchema, SchemaShape } from "./jsonSchema"

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
    const host = first(schemaToFields(POSTGRES_SCHEMA))

    expect(host.label).toBe("Host")
  })

  it("falls back to the property name when there is no title", () => {
    const fields = schemaToFields({
      type: "object",
      properties: { plain_name: { type: "string" } },
    })

    expect(at(fields, 0).label).toBe("plain_name")
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

    expect(at(fields, 0).kind).toBe("boolean")
    expect(at(fields, 1).kind).toBe("select")
    expect(at(fields, 1).choices).toEqual([
      { value: "require", label: "require" },
      { value: "disable", label: "disable" },
    ])
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

describe("the layout a field declares", () => {
  const schema: JsonSchema = {
    properties: {
      host: { type: "string", title: "Host", group: "general", row: "address" },
      port: { type: "integer", title: "Port", group: "general", row: "address" },
      database: { type: "string", title: "Database", group: "general" },
      key: { type: "string", title: "Key", group: "ssl" },
    },
    required: ["host", "database"],
  }

  it("carries the group and the row onto the field", () => {
    const host = first(schemaToFields(schema))

    expect(host.group).toBe("general")
    expect(host.row).toBe("address")
  })

  it("defaults a field that declares nothing to the general group", () => {
    const only = first(schemaToFields({ properties: { a: { type: "string" } } }))

    expect(only.group).toBe("general")
    expect(only.row).toBeUndefined()
  })

  it("puts fields of one row on one line, in declaration order", () => {
    const lines = fieldRows(schemaToFields(schema).filter((f) => f.group === "general"))

    expect(lines.map((line) => line.map((f) => f.name))).toEqual([
      ["host", "port"],
      ["database"],
    ])
  })

  it("does not merge two runs of the same row name that are not adjacent", () => {
    // Otherwise a field could jump up the form to join a row above it.
    const fields = schemaToFields({
      properties: {
        a: { type: "string", row: "pair" },
        b: { type: "string" },
        c: { type: "string", row: "pair" },
      },
    })

    expect(fieldRows(fields).map((line) => line.map((f) => f.name))).toEqual([
      ["a"],
      ["b"],
      ["c"],
    ])
  })

  it("groups fields into tabs, keeping the order the schema gave", () => {
    expect(fieldGroups(schemaToFields(schema)).map((g) => g.id)).toEqual([
      "general",
      "ssl",
    ])
  })
})

// Copied from GET /api/v1/adapter-types/ once PostgreSQL options became a
// discriminated union: the exact shape Pydantic emits for one.
const UNION_SCHEMA: JsonSchema = {
  $defs: {
    PostgresNoAuth: {
      type: "object",
      title: "No auth",
      required: ["host", "database", "user"],
      properties: {
        host: {
          type: "string",
          title: "Host",
          minLength: 1,
          group: "general",
          row: "address",
        },
        port: {
          type: "integer",
          title: "Port",
          default: 5432,
          group: "general",
          row: "address",
        },
        database: { type: "string", title: "Database", minLength: 1, group: "general" },
        auth_method: {
          const: "no_auth",
          default: "no_auth",
          title: "Authentication",
          type: "string",
          group: "general",
        },
        user: { type: "string", title: "User", minLength: 1, group: "general" },
      },
    },
    PostgresUserPassword: {
      type: "object",
      title: "User & Password",
      required: ["host", "database", "user", "password"],
      properties: {
        host: {
          type: "string",
          title: "Host",
          minLength: 1,
          group: "general",
          row: "address",
        },
        port: {
          type: "integer",
          title: "Port",
          default: 5432,
          group: "general",
          row: "address",
        },
        database: { type: "string", title: "Database", minLength: 1, group: "general" },
        auth_method: {
          const: "user_password",
          default: "user_password",
          title: "Authentication",
          type: "string",
          group: "general",
        },
        user: { type: "string", title: "User", minLength: 1, group: "general" },
        password: {
          type: "string",
          title: "Password",
          format: "password",
          writeOnly: true,
          group: "general",
        },
      },
    },
  },
  // The order of oneOf is the order the variants were declared in; the keys of
  // mapping are not.
  discriminator: {
    propertyName: "auth_method",
    mapping: {
      no_auth: "#/$defs/PostgresNoAuth",
      user_password: "#/$defs/PostgresUserPassword",
    },
  },
  oneOf: [{ $ref: "#/$defs/PostgresUserPassword" }, { $ref: "#/$defs/PostgresNoAuth" }],
}

function variantsOf(shape: SchemaShape) {
  if (shape.kind !== "variants") throw new Error("expected a union schema")
  return shape
}

describe("readSchema", () => {
  it("reads a schema with no variants as a plain list of fields", () => {
    const shape = readSchema(POSTGRES_SCHEMA)

    expect(shape.kind).toBe("plain")
    expect(shape.kind === "plain" && shape.fields.map((f) => f.name)).toEqual([
      "host",
      "port",
      "database",
      "user",
      "password",
    ])
  })

  it("follows a $ref into $defs rather than reading the top level", () => {
    // Nothing but $defs, oneOf and the discriminator is at the top level of a
    // union schema: reading `properties` there would find no fields at all.
    const shape = variantsOf(readSchema(UNION_SCHEMA))

    expect(keyed(shape.byVariant, "user_password").map((f) => f.name)).toEqual([
      "password",
    ])
  })

  it("draws the fields every variant shares only once", () => {
    // What stops the address jumping about when the method is switched.
    const shape = variantsOf(readSchema(UNION_SCHEMA))

    expect(shape.common.map((f) => f.name)).toEqual(["host", "port", "database", "user"])
  })

  it("keeps the common fields in the order of the first variant", () => {
    const shape = variantsOf(readSchema(UNION_SCHEMA))

    expect(shape.common.map((f) => f.row)).toEqual([
      "address",
      "address",
      undefined,
      undefined,
    ])
  })

  it("never leaves the discriminator among the fields it lists", () => {
    // It is drawn from the mapping instead; left in, it would render as a
    // text input holding the name of the variant.
    const shape = variantsOf(readSchema(UNION_SCHEMA))

    expect(shape.common.map((f) => f.name)).not.toContain("auth_method")
    for (const fields of Object.values(shape.byVariant)) {
      expect(fields.map((f) => f.name)).not.toContain("auth_method")
    }
  })

  it("offers the ways of connecting as a select of code and wording", () => {
    const shape = variantsOf(readSchema(UNION_SCHEMA))

    expect(shape.discriminator.kind).toBe("select")
    expect(shape.discriminator.name).toBe("auth_method")
    expect(shape.discriminator.choices).toEqual([
      { value: "user_password", label: "User & Password" },
      { value: "no_auth", label: "No auth" },
    ])
  })

  it("labels the choice with what the server called the field", () => {
    const shape = variantsOf(readSchema(UNION_SCHEMA))

    expect(shape.discriminator.label).toBe("Authentication")
    expect(shape.discriminator.group).toBe("general")
  })

  it("starts on the first variant", () => {
    const shape = variantsOf(readSchema(UNION_SCHEMA))

    expect(shape.discriminator.defaultValue).toBe("user_password")
    expect(defaultValues([shape.discriminator]).auth_method).toBe("user_password")
  })

  it("names a variant by its class when the model declared no title", () => {
    const shape = variantsOf(
      readSchema({
        $defs: { Bare: { type: "object", properties: { a: { type: "string" } } } },
        discriminator: { propertyName: "kind", mapping: { bare: "#/$defs/Bare" } },
        oneOf: [{ $ref: "#/$defs/Bare" }],
      })
    )

    expect(shape.discriminator.choices).toEqual([{ value: "bare", label: "Bare" }])
  })

  it("keeps a field of the same name but a different kind out of the common ones", () => {
    const shape = variantsOf(
      readSchema({
        $defs: {
          A: {
            type: "object",
            title: "A",
            properties: {
              k: { const: "a", type: "string" },
              token: { type: "string", title: "Token" },
            },
          },
          B: {
            type: "object",
            title: "B",
            properties: {
              k: { const: "b", type: "string" },
              token: { type: "integer", title: "Token" },
            },
          },
        },
        discriminator: { propertyName: "k", mapping: { a: "#/$defs/A", b: "#/$defs/B" } },
        oneOf: [{ $ref: "#/$defs/A" }, { $ref: "#/$defs/B" }],
      })
    )

    expect(shape.common).toEqual([])
    expect(keyed(shape.byVariant, "a").map((f) => f.name)).toEqual(["token"])
    expect(keyed(shape.byVariant, "b").map((f) => f.name)).toEqual(["token"])
  })
})

describe("the schema a chosen variant is validated against", () => {
  it("accepts the common fields plus the ones of the variant in hand", () => {
    const shape = variantsOf(readSchema(UNION_SCHEMA))
    const fields = [...shape.common, shape.discriminator, ...keyed(shape.byVariant, "no_auth")]

    const result = fieldsToZod(fields).safeParse({
      auth_method: "no_auth",
      host: "db",
      port: 5432,
      database: "app",
      user: "ann",
    })

    expect(result.success).toBe(true)
  })

  it("does not demand a field belonging to another variant", () => {
    // The whole union at once would insist on a password that this way of
    // connecting does not have.
    const shape = variantsOf(readSchema(UNION_SCHEMA))
    const withPassword = [
      ...shape.common,
      shape.discriminator,
      ...keyed(shape.byVariant, "user_password"),
    ]

    const result = fieldsToZod(withPassword).safeParse({
      auth_method: "user_password",
      host: "db",
      port: 5432,
      database: "app",
      user: "ann",
    })

    expect(result.success).toBe(false)
  })
})

describe("a choice offered by an enum", () => {
  it("carries a code and a wording, the same as a variant does", () => {
    const fields = schemaToFields({
      properties: {
        mode: { type: "string", title: "Mode", enum: ["require", "disable"] },
      },
    })

    expect(first(fields).choices).toEqual([
      { value: "require", label: "require" },
      { value: "disable", label: "disable" },
    ])
  })
})
