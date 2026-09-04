import { describe, expect, it } from "vitest"

import { deliveryGraph } from "./fixtures"
import { edgesOf, graphProblem, groupGraph, neighborsOf, GRAPH_LIMITS } from "./model"

describe("a graph of services and ports", () => {
  it("selects only connections on the chosen port, including self references", () => {
    expect(graphProblem(deliveryGraph)).toBeNull()
    expect(edgesOf(deliveryGraph, { kind: "node", id: "api", portId: "events" }).map((edge) => edge.id)).toEqual(["jobs"])
    expect(neighborsOf(deliveryGraph, { kind: "edge", id: "retry" })).toEqual(new Set(["worker"]))
    expect(neighborsOf(deliveryGraph, { kind: "node", id: "api" })).toEqual(new Set(["api", "worker", "monitor"]))
  })

  it("filters a group without dangling connections or changing the document", () => {
    const filtered = groupGraph(deliveryGraph, "delivery")
    expect(filtered.nodes.map((node) => node.id)).toEqual(["api", "worker"])
    expect(filtered.edges.map((edge) => edge.id)).toEqual(["jobs", "retry"])
    expect(graphProblem(filtered)).toBeNull()
    expect(deliveryGraph.nodes).toHaveLength(3)
    expect(groupGraph(deliveryGraph, null)).toBe(deliveryGraph)
  })

  it("refuses missing ports and repeated identities before rendering", () => {
    expect(graphProblem({ ...deliveryGraph, nodes: [...deliveryGraph.nodes, deliveryGraph.nodes[0]!] })).toContain("duplicate")
    expect(graphProblem({ ...deliveryGraph, nodes: deliveryGraph.nodes.filter((node) => node.id !== "worker") })).toContain("missing")
    const edge = deliveryGraph.edges[0]!
    expect(graphProblem({ ...deliveryGraph, edges: [{ ...edge, target: { nodeId: "worker", portIds: ["absent"] } }] })).toContain("missing")
    expect(graphProblem({ ...deliveryGraph, edges: [edge, edge] })).toContain("duplicate")
  })

  it("refuses oversized documents instead of dropping their contents", () => {
    expect(graphProblem({ nodes: Array.from({ length: GRAPH_LIMITS.nodes + 1 }, (_, id) => ({ id: String(id), label: "Node", rows: [] })), edges: [], groups: [] })).toContain("too large")
    expect(graphProblem({ nodes: [{ id: "a", label: "A", rows: Array.from({ length: GRAPH_LIMITS.rows + 1 }, (_, id) => ({ id: String(id), label: "Port" })) }], edges: [], groups: [] })).toContain("too large")
  })
})
