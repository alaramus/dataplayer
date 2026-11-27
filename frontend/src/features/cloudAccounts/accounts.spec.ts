import { describe, expect, it } from "vitest"

import type { CloudAccountPublic } from "@/client"
import type { FieldSpec, JsonSchema } from "@/shared/SchemaForm/jsonSchema"

import { accountFields, settingsFor, withAccountChoices } from "./accounts"

function account(id: string, kind: CloudAccountPublic["kind"], name: string): CloudAccountPublic {
  return {
    id,
    name,
    kind,
    kind_title: kind,
    method: `${kind}_x`,
    method_title: "Access key",
    settings: {},
    stored_secrets: [],
    ambient: false,
    testable: false,
    created_at: null,
    updated_at: null,
    used_by: [],
  }
}

const accountField: FieldSpec = {
  name: "account",
  label: "Account",
  kind: "text",
  required: true,
  purpose: "cloud-account",
  accountKind: "aws",
  group: "general",
}

describe("withAccountChoices", () => {
  it("offers only the owner's accounts of the kind the field takes", () => {
    const [field] = withAccountChoices(
      [accountField],
      [account("1", "aws", "prod"), account("2", "vault", "vault"), account("3", "aws", "dev")]
    )

    expect(field?.kind).toBe("select")
    expect(field?.choices).toEqual([
      { value: "1", label: "prod · Access key" },
      { value: "3", label: "dev · Access key" },
    ])
  })

  it("leaves every other field as it is", () => {
    const other: FieldSpec = { ...accountField, name: "host", purpose: undefined, accountKind: undefined }

    expect(withAccountChoices([other], [account("1", "aws", "prod")])).toEqual([other])
  })
})

const union: JsonSchema = {
  oneOf: [{ $ref: "#/$defs/Key" }, { $ref: "#/$defs/Chain" }],
  discriminator: { propertyName: "method", mapping: { key: "#/$defs/Key", chain: "#/$defs/Chain" } },
  $defs: {
    Key: {
      title: "Access key",
      properties: {
        method: { type: "string", const: "key", default: "key", title: "Method" },
        region: { type: "string", title: "Region" },
        secret: { type: "string", format: "password", writeOnly: true, title: "Secret" },
      },
    },
    Chain: {
      title: "This server's credentials",
      properties: {
        method: { type: "string", const: "chain", default: "chain", title: "Method" },
        region: { type: "string", title: "Region" },
      },
    },
  },
}

describe("accountFields", () => {
  it("draws the fields of the method chosen, the first when none is", () => {
    expect(accountFields(union, "chain").map((field) => field.name)).toEqual(["method", "region"])
    expect(accountFields(union, undefined).map((field) => field.name)).toEqual(["method", "region", "secret"])
  })

  it("draws a kind with one method as it is", () => {
    const plain = union.$defs?.Key as JsonSchema

    expect(accountFields(plain, "anything").map((field) => field.name)).toEqual(["method", "region", "secret"])
  })
})

describe("settingsFor", () => {
  it("sends only what the chosen method shows", () => {
    const fields = accountFields(union, "chain")

    expect(settingsFor(fields, { method: "chain", region: "eu", secret: "left over" })).toEqual({
      method: "chain",
      region: "eu",
    })
  })
})
