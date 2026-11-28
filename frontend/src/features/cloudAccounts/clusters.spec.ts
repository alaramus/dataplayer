import { describe, expect, it } from "vitest"

import type { FieldSpec } from "@/shared/SchemaForm/jsonSchema"

import { clusterAccount, withClusterChoices } from "./clusters"

const account: FieldSpec = {
  name: "account",
  label: "Google Cloud account",
  kind: "select",
  required: true,
  purpose: "cloud-account",
  accountKinds: ["gcp"],
  group: "general",
}
const cluster: FieldSpec = { name: "cluster", label: "Cluster", kind: "text", required: true, purpose: "gke-cluster", group: "general" }
const CLUSTERS = [{ name: "projects/p/locations/l/clusters/a", title: "a · l · p" }]

describe("withClusterChoices", () => {
  it("offers the account's clusters, keeping one the list does not hold", () => {
    const [field] = withClusterChoices([cluster], CLUSTERS, { cluster: "projects/p/locations/l/clusters/gone" })

    expect(field?.kind).toBe("select")
    expect(field?.choices?.map((one) => one.value)).toEqual([
      "projects/p/locations/l/clusters/a",
      "projects/p/locations/l/clusters/gone",
    ])
  })

  it("leaves the field typed while there is no list", () => {
    expect(withClusterChoices([cluster], [], {})).toEqual([cluster])
  })
})

describe("clusterAccount", () => {
  it("is the account a form with a cluster field names", () => {
    expect(clusterAccount([account, cluster], { account: "a1" })).toBe("a1")
    expect(clusterAccount([account], { account: "a1" })).toBeUndefined()
    expect(clusterAccount([account, cluster], { account: "" })).toBeUndefined()
  })
})
