import { describe, expect, it } from "vitest"

import { at, first, keyed } from "@/shared/testing/collections"

import {
  choicesOf,
  defaultValues,
  defaultsOf,
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

  it("gives a value written on several lines a box, and only that value", () => {
    // Said by the model that declares the field: the type is `string` either
    // way, and a form inferring "long" from "string" would give every host
    // name six lines.
    const fields = schemaToFields({
      type: "object",
      properties: {
        name: { type: "string", title: "Key" },
        value: { type: "string", title: "Fields", "x-ui-multiline": true },
      },
    })

    expect(at(fields, 0).kind).toBe("text")
    expect(at(fields, 1).kind).toBe("multiline")
  })

  it("carries what the source says about a field, for the line under it", () => {
    // It was travelling in the schema and being dropped on the floor: "one per
    // line, as field=value" is a fact about a Redis hash that no form can work
    // out for itself.
    const fields = schemaToFields({
      type: "object",
      properties: {
        value: {
          type: "string",
          title: "Fields",
          description: "One per line, written as field=value",
        },
      },
    })

    expect(first(fields).description).toBe("One per line, written as field=value")
    expect(schemaToFields(POSTGRES_SCHEMA)[0]?.description).toBeUndefined()
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

describe("what a source publishes about a choice", () => {
  const schema = {
    type: "object",
    properties: {
      dialect: {
        type: "string",
        title: "Written as",
        default: "dbml",
        enum: ["sqlalchemy", "dbml"],
        "x-ui-choices": [
          { value: "sqlalchemy", label: "SQLAlchemy" },
          { value: "dbml", label: "DBML (dbdiagram.io)" },
        ],
      },
      plain: { type: "string", enum: ["a", "b"] },
      nothing: { type: "string" },
    },
  } as const

  it("prefers the source's words for a value over the value", () => {
    // `dbml` is a value; "DBML (dbdiagram.io)" is what somebody recognises,
    // and only the source knows the difference.
    const fields = schemaToFields(schema as unknown as JsonSchema)

    expect(at(fields, 0).choices).toEqual([
      { value: "sqlalchemy", label: "SQLAlchemy" },
      { value: "dbml", label: "DBML (dbdiagram.io)" },
    ])
    expect(at(fields, 1).choices).toEqual([
      { value: "a", label: "a" },
      { value: "b", label: "b" },
    ])
  })

  it("is readable without building a form at all", () => {
    // A workflow's schema may hold a property no form can render, and asking
    // for its fields is meant to fail loudly.
    expect(choicesOf(schema as unknown as JsonSchema)).toEqual({
      dialect: [
        { value: "sqlalchemy", label: "SQLAlchemy" },
        { value: "dbml", label: "DBML (dbdiagram.io)" },
      ],
    })
    expect(defaultsOf(schema as unknown as JsonSchema)).toEqual({ dialect: "dbml" })
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
      required: ["database", "user"],
      properties: {
        host: {
          type: "string",
          title: "Host",
          default: "localhost",
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
        auth_method: {
          const: "no_auth",
          default: "no_auth",
          title: "Authentication",
          type: "string",
          group: "general",
        },
        database: { type: "string", title: "Database", minLength: 1, group: "general" },
        user: { type: "string", title: "User", minLength: 1, group: "general" },
      },
    },
    PostgresUserPassword: {
      type: "object",
      title: "User & Password",
      required: ["database", "user", "password"],
      properties: {
        host: {
          type: "string",
          title: "Host",
          default: "localhost",
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
        auth_method: {
          const: "user_password",
          default: "user_password",
          title: "Authentication",
          type: "string",
          group: "general",
        },
        database: { type: "string", title: "Database", minLength: 1, group: "general" },
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
      "host",
      "port",
      "auth_method",
      "database",
      "user",
      "password",
    ])
  })

  it("leaves the choice where the model declared it", () => {
    // The server states the order by declaring the fields in it. Gathering
    // every shared field first and putting the choice after them would be a
    // rule of the form's own, and it would put the choice under the database.
    const shape = variantsOf(readSchema(UNION_SCHEMA))
    const names = keyed(shape.byVariant, "no_auth").map((f) => f.name)

    expect(names.indexOf("auth_method")).toBe(names.indexOf("port") + 1)
  })

  it("draws the fields every variant shares only once", () => {
    // What stops the address jumping about when the method is switched.
    const shape = variantsOf(readSchema(UNION_SCHEMA))

    expect(shape.common.map((f) => f.name)).toEqual(["host", "port", "database", "user"])
  })

  it("shows the discriminator as a select and never as the const it arrives as", () => {
    // Pydantic emits the property as a `const`, which would render as a text
    // box holding the name of the variant.
    const shape = variantsOf(readSchema(UNION_SCHEMA))
    const inPlace = keyed(shape.byVariant, "no_auth").find((f) => f.name === "auth_method")

    expect(inPlace?.kind).toBe("select")
    expect(inPlace).toBe(shape.discriminator)
    // And it is never counted as a field the variants merely share.
    expect(shape.common.map((f) => f.name)).not.toContain("auth_method")
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
    expect(keyed(shape.byVariant, "a").map((f) => f.name)).toEqual(["k", "token"])
    expect(keyed(shape.byVariant, "b").map((f) => f.name)).toEqual(["k", "token"])
  })
})

describe("the schema a chosen variant is validated against", () => {
  it("accepts the common fields plus the ones of the variant in hand", () => {
    const shape = variantsOf(readSchema(UNION_SCHEMA))
    const result = fieldsToZod(keyed(shape.byVariant, "no_auth")).safeParse({
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
    const result = fieldsToZod(keyed(shape.byVariant, "user_password")).safeParse({
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

describe("a field that may be left out", () => {
  /**
   * Pydantic writes `int | None` as two branches, and puts the bounds inside
   * the branch that is not null. Before this, such a field reached `kindOf`
   * with no type at all and threw — which is what a Redis key's optional
   * expiry did the first time it was drawn.
   */
  const optional: JsonSchema = {
    type: "object",
    properties: {
      ttl_seconds: {
        anyOf: [
          { type: "integer", minimum: 1, maximum: 600 },
          { type: "null" },
        ],
        title: "Expires in (seconds)",
        default: null,
      },
    },
    required: [],
  }

  it("is an ordinary field that is not required", () => {
    const [field] = schemaToFields(optional)

    expect(field?.kind).toBe("number")
    expect(field?.required).toBe(false)
    expect(field?.label).toBe("Expires in (seconds)")
  })

  it("keeps the bounds that live inside the branch", () => {
    const [field] = schemaToFields(optional)

    expect(field?.minimum).toBe(1)
    expect(field?.maximum).toBe(600)
  })

  it("still fails loudly on a union of two real types", () => {
    // A form for "either a number or a list of column mappings" is a form
    // nobody has designed, and silence would leave the field unrendered.
    expect(() =>
      schemaToFields({
        type: "object",
        properties: {
          whatever: { anyOf: [{ type: "integer" }, { type: "array" }] },
        },
      })
    ).toThrow(/Unsupported property type/)
  })
})
