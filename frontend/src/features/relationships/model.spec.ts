import { describe, expect, it } from "vitest"

import type { RelationModel } from "@/client"
import { graphProblem } from "@/shared/graph/model"
import { diagramNodes, relationGraph, relationshipPanelId } from "./model"

const columns = (names: string[]): NonNullable<RelationModel["columns"]> => names.map((name, position) => ({ name, position, nullable: false, type: { sql: "integer", category: "number" } }))
const orders: RelationModel = {
  node_id: "opaque/orders", name: "Orders", schema_name: "Sales", kind: "table", columns: columns(["tenant", "customer", "id"]),
  constraints: [
    { kind: "primary_key", name: "orders_pk", columns: ["tenant", "id"] },
    { kind: "foreign_key", name: "customer_fk", columns: ["tenant", "customer"], target_node_id: "opaque/customers", target_columns: ["tenant", "id"], on_delete: "cascade" },
    { kind: "foreign_key", name: "parent_fk", columns: ["tenant", "customer"], target_node_id: "opaque/orders", target_columns: ["tenant", "id"] },
  ],
}
const customers: RelationModel = { node_id: "opaque/customers", name: "Customers", schema_name: "CRM", kind: "table", columns: columns(["tenant", "id"]) }
const requested = [orders, customers].map((model) => ({ id: model.node_id, label: model.name }))

describe("the relation graph producer", () => {
  it("preserves compound keys as one edge with all pairs and real column ports", () => {
    const graph = relationGraph({ requested, models: [orders, customers], failures: [] })
    expect(graphProblem(graph)).toBeNull()
    const edge = graph.edges.find((edge) => edge.label === "customer_fk")!
    expect(edge.source.portIds).toEqual(["tenant", "customer"])
    expect(edge.target.portIds).toEqual(["tenant", "id"])
    expect(edge.details).toContainEqual({ label: "Columns", value: "tenant → tenant\ncustomer → id" })
    expect(edge.details).toContainEqual({ label: "On delete", value: "cascade" })
    expect(graph.edges).toHaveLength(2)
    expect(graph.nodes[0]!.rows[0]!.badges).toEqual(["PK", "FK"])
    expect(graph.edges[1]!.source.nodeId).toBe(graph.edges[1]!.target.nodeId)
    expect(graph.groups).toEqual([{ id: "Sales", label: "Sales" }, { id: "CRM", label: "CRM" }])
  })

  it("retains parallel constraints with different identities", () => {
    const fk = orders.constraints![1]!
    const graph = relationGraph({ requested, models: [{ ...orders, constraints: [fk, { ...fk, name: "second_fk" }] }, customers], failures: [] })
    expect(graph.edges).toHaveLength(2)
    expect(graph.edges[0]!.id).not.toBe(graph.edges[1]!.id)
  })

  it("distinguishes an unloaded target from a failed requested structure without parsing its id", () => {
    const outside = relationGraph({ requested: [requested[0]!], models: [orders], failures: [] })
    expect(outside.nodes.find((node) => node.id === customers.node_id)).toMatchObject({ label: customers.node_id, caption: "Outside selection", rows: [], placeholder: true })
    expect(outside.edges[0]).toMatchObject({ dashed: true, target: { nodeId: customers.node_id, portIds: [] } })
    expect(graphProblem(outside)).toBeNull()
    const failed = relationGraph({ requested, models: [orders], failures: [{ ...requested[1]!, message: "Access denied" }] })
    expect(failed.nodes[1]).toMatchObject({ label: "Customers", caption: "Structure unavailable", details: [{ label: "Read error", value: "Access denied" }] })
    expect(graphProblem(failed)).toBeNull()
  })

  it("does not infer foreign keys from similar column names", () => {
    expect(relationGraph({ requested, models: [{ ...orders, constraints: [] }, customers], failures: [] }).edges).toEqual([])
  })

  it("uses the explicit checks even when none can be described, otherwise the filtered list", () => {
    const table = { id: "t", label: "T", describable: true }
    const file = { id: "f", label: "F", describable: false }
    expect(diagramNodes([], [table, file])).toEqual([{ id: "t", label: "T" }])
    expect(diagramNodes([file], [table])).toEqual([])
    expect(diagramNodes([table], [])).toEqual([{ id: "t", label: "T" }])
    expect(relationshipPanelId("c", requested)).toBe(relationshipPanelId("c", [...requested].reverse()))
    expect(relationshipPanelId("c", requested)).not.toBe(relationshipPanelId("c", [requested[0]!]))
  })
})
