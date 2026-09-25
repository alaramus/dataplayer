import { describe, expect, it } from "vitest"

import type { GraphDocument, Point2 } from "./model"
import { arrange3, isLegacyFlat3 } from "./layout3d"

const graph: GraphDocument = {
  groups: [{ id: "one", label: "One" }],
  nodes: ["a", "b", "c", "d", "e", "f"].map((id) => ({
    id, label: id, groupId: "one", rows: [],
  })),
  edges: [
    ["a", "b"], ["b", "c"], ["c", "d"], ["d", "e"], ["e", "f"],
  ].map(([source, target]) => ({
    id: `${source}-${target}`, label: "Link", directed: true,
    source: { nodeId: source! }, target: { nodeId: target! },
  })),
}
const sketch: Record<string, Point2> = Object.fromEntries(
  graph.nodes.map((node, index) => [node.id, { x: index * 300, y: 0 }])
)

describe("volumetric graph layout", () => {
  it("places one group at different depths without changing the 2D sketch", () => {
    const before = JSON.stringify({ graph, sketch })
    const placed = arrange3(graph, sketch)
    const reversed = arrange3(
      { ...graph, nodes: [...graph.nodes].reverse(), edges: [...graph.edges].reverse() },
      sketch,
    )

    expect(placed).toEqual(reversed)
    expect(JSON.stringify({ graph, sketch })).toBe(before)
    const heights = Object.values(placed).map((point) => point.y)
    expect(Math.max(...heights) - Math.min(...heights)).toBeGreaterThan(40)
    for (const [index, a] of graph.nodes.entries()) {
      const first = placed[a.id]!
      expect(Object.values(first).every(Number.isFinite)).toBe(true)
      for (const b of graph.nodes.slice(index + 1)) {
        const second = placed[b.id]!
        expect(Math.hypot(first.x - second.x, first.y - second.y, first.z - second.z)).toBeGreaterThan(150)
      }
    }
  })

  it("upgrades only the old untouched projection", () => {
    const old = Object.fromEntries(graph.nodes.map((node) => [node.id, {
      x: sketch[node.id]!.x * 0.7,
      y: 0,
      z: sketch[node.id]!.y * 0.55,
    }]))
    expect(isLegacyFlat3(graph, sketch, old)).toBe(true)
    expect(isLegacyFlat3(graph, sketch, {
      ...old, c: { ...old.c!, y: 5 },
    })).toBe(false)
    expect(isLegacyFlat3(graph, sketch, arrange3(graph, sketch))).toBe(false)
  })
})
