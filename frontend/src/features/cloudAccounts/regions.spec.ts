import { describe, expect, it } from "vitest"

import type { FieldSpec } from "@/shared/SchemaForm/jsonSchema"
import { schemaToFields } from "@/shared/SchemaForm/jsonSchema"

import { regionAccount, withRegionChoices } from "./regions"

const regions = [
  { name: "eu-central-1", title: "Europe (Frankfurt)" },
  { name: "us-south-1", title: "" },
]

const region: FieldSpec = {
  name: "region",
  label: "Region",
  kind: "text",
  required: false,
  purpose: "aws-region",
  group: "general",
}

const s3Region: FieldSpec = { ...region, typedWhen: "endpoint" }

const host: FieldSpec = { name: "host", label: "Host", kind: "text", required: true, group: "general" }

describe("withRegionChoices", () => {
  it("offers the empty choice first, then each region by its name and title", () => {
    const [field] = withRegionChoices([region], regions, {}, "Default")

    expect(field?.kind).toBe("select")
    expect(field?.choices).toEqual([
      { value: "", label: "Default" },
      { value: "eu-central-1", label: "eu-central-1 · Europe (Frankfurt)" },
      { value: "us-south-1", label: "us-south-1" },
    ])
  })

  it("keeps a region the form holds and the list does not", () => {
    const [field] = withRegionChoices([region], regions, { region: "ap-south-2" }, "Default")

    expect(field?.choices?.at(-1)).toEqual({ value: "ap-south-2", label: "ap-south-2" })
  })

  it("leaves the field typed without a list, and other fields alone", () => {
    expect(withRegionChoices([region, host], [], {}, "Default")).toEqual([region, host])
    expect(withRegionChoices([host], regions, {}, "Default")).toEqual([host])
  })

  it("leaves an S3 region typed while an endpoint names another provider's store", () => {
    const [typed] = withRegionChoices([s3Region], regions, { endpoint: "https://minio.local:9000" }, "Default")
    const [chosen] = withRegionChoices([s3Region], regions, { endpoint: " " }, "Default")

    expect(typed).toEqual(s3Region)
    expect(chosen?.kind).toBe("select")
  })

  it("reads the purpose and the typed-when field from the schema", () => {
    const [field] = schemaToFields({
      type: "object",
      properties: {
        region: { type: "string", "x-ui-purpose": "aws-region", "x-ui-typed-when": "endpoint" },
      },
    })

    expect(field?.purpose).toBe("aws-region")
    expect(field?.typedWhen).toBe("endpoint")
  })
})

describe("regionAccount", () => {
  const account: FieldSpec = {
    name: "account",
    label: "AWS account",
    kind: "select",
    required: true,
    purpose: "cloud-account",
    accountKinds: ["aws"],
    group: "general",
  }

  it("is the AWS account the form names, and nothing before one is chosen", () => {
    expect(regionAccount([account, region], { account: "a-1" })).toBe("a-1")
    expect(regionAccount([account, region], { account: "" })).toBeUndefined()
    expect(regionAccount([region], {})).toBeUndefined()
  })

  it("is never a secret store, which takes accounts of four kinds", () => {
    const store = { ...account, accountKinds: ["aws", "gcp", "azure", "vault"] }

    expect(regionAccount([store, region], { account: "a-1" })).toBeUndefined()
  })
})
