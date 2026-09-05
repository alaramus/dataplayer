import { describe, expect, it } from "vitest"

import type { DeclaredReferencePublic, FetchColumn, ReferenceEndPublic } from "@/client"

import { farLabel, lookupColumns, sidesFrom } from "./model"

function end(
  connectorId: string,
  nodeId: string,
  column: string,
  names: { connector: string; node: string }
): ReferenceEndPublic {
  return {
    connector_id: connectorId,
    node_id: nodeId,
    column,
    connector_name: names.connector,
    adapter_type: "postgres",
    node_label: names.node,
  }
}

const relation = end("warehouse", "sales.regions", "code", {
  connector: "Warehouse",
  node: "regions",
})
const csv = end("files", "regions.csv", "code", {
  connector: "My files",
  node: "regions.csv",
})
const reference: DeclaredReferencePublic = {
  id: "ref-1",
  ends: [relation, csv],
  created_at: null,
}

function column(name: string, operators: FetchColumn["filter_operators"]): FetchColumn {
  return {
    name,
    type: { sql: "text", category: "string" },
    filter_operators: operators,
  }
}

describe("which columns a reference can stand on", () => {
  it("keeps the ones the source can look a value up in", () => {
    const columns = [column("code", ["eq", "ne"]), column("picture", [])]

    expect(lookupColumns(columns).map((found) => found.name)).toEqual(["code"])
  })

  it("keeps none when the source states no operators at all", () => {
    expect(lookupColumns([column("code", undefined)])).toEqual([])
  })
})

describe("which end you are standing on", () => {
  it("finds the near end whichever way round the pair was stored", () => {
    expect(sidesFrom(reference, "warehouse", "sales.regions")).toEqual({
      near: relation,
      far: csv,
    })
    expect(sidesFrom(reference, "files", "regions.csv")).toEqual({
      near: csv,
      far: relation,
    })
  })

  it("finds nothing when neither end is this node", () => {
    expect(sidesFrom(reference, "warehouse", "sales.customers")).toBeNull()
  })

  it("does not confuse the same node id in another connection", () => {
    expect(sidesFrom(reference, "elsewhere", "sales.regions")).toBeNull()
  })
})

describe("how the far end reads", () => {
  it("names the connection when it is a different one", () => {
    expect(farLabel(csv, "warehouse")).toBe("My files · regions.csv.code")
  })

  it("says only the node inside one source", () => {
    expect(farLabel(relation, "warehouse")).toBe("regions.code")
  })
})
