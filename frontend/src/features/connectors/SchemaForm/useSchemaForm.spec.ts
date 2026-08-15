import { describe, expect, it } from "vitest"

import { jsonSchemaToZod, schemaToFields } from "./jsonSchema"
import type { JsonSchema } from "./jsonSchema"
import { useSchemaForm } from "./useSchemaForm"

const SCHEMA: JsonSchema = {
  type: "object",
  required: ["host"],
  properties: {
    host: { type: "string", title: "Host", minLength: 1 },
    port: { type: "integer", title: "Port", default: 5432 },
  },
}

describe("useSchemaForm", () => {
  it("fills values with schema defaults on reset", () => {
    const form = useSchemaForm()

    form.reset(schemaToFields(SCHEMA))

    expect(form.values.value).toEqual({ host: "", port: 5432 })
  })

  it("reports an error for an empty required field", () => {
    const form = useSchemaForm()
    form.reset(schemaToFields(SCHEMA))

    const valid = form.validate(jsonSchemaToZod(SCHEMA))

    expect(valid).toBe(false)
    expect(form.errors.value.host).toBeTruthy()
  })

  it("clears errors once the values become valid", () => {
    const form = useSchemaForm()
    form.reset(schemaToFields(SCHEMA))
    form.validate(jsonSchemaToZod(SCHEMA))

    form.values.value.host = "localhost"
    const valid = form.validate(jsonSchemaToZod(SCHEMA))

    expect(valid).toBe(true)
    expect(form.errors.value).toEqual({})
  })

  it("maps a server 422 response onto field errors", () => {
    const form = useSchemaForm()
    form.reset(schemaToFields(SCHEMA))

    form.applyServerErrors([
      { loc: ["body", "options", "host"], msg: "Host is unreachable", type: "value_error" },
    ])

    expect(form.errors.value.host).toBe("Host is unreachable")
  })

  it("ignores server errors that do not point at a field", () => {
    const form = useSchemaForm()
    form.reset(schemaToFields(SCHEMA))

    form.applyServerErrors([{ loc: ["body"], msg: "Invalid body", type: "value_error" }])

    expect(form.errors.value).toEqual({})
  })

  it("applies supplied initial values on top of the defaults", () => {
    const form = useSchemaForm()

    form.reset(schemaToFields(SCHEMA), { host: "db.internal" })

    expect(form.values.value).toEqual({ host: "db.internal", port: 5432 })
  })
})
