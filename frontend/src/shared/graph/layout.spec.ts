import { describe, expect, it } from "vitest"

import { deliveryGraph } from "./fixtures"
import { arrange, CARD_WIDTH, edgePaths, fit2, HEADER_HEIGHT, nodeHeight, ROW_HEIGHT, zoomAt } from "./layout"

describe("graph geometry", () => {
  it("places cyclic and disconnected components deterministically without overlapping cards", () => {
    const graph = { ...deliveryGraph, nodes: [...deliveryGraph.nodes, { id: "offline", label: "Offline", rows: [] }] }
    const before = JSON.stringify(graph)
    const result = arrange(graph, true)
    const reversed = arrange({ ...graph, nodes: [...graph.nodes].reverse(), edges: [...graph.edges].reverse() }, true)
    expect(result).toEqual(reversed)
    expect(JSON.stringify(graph)).toBe(before)
    for (const [index, a] of graph.nodes.entries()) {
      const p = result.positions2[a.id]!
      expect(Number.isFinite(result.positions3[a.id]!.z)).toBe(true)
      for (const b of graph.nodes.slice(index + 1)) {
        const q = result.positions2[b.id]!
        expect(p.x + CARD_WIDTH <= q.x || q.x + CARD_WIDTH <= p.x || p.y + nodeHeight(a, true) <= q.y || q.y + nodeHeight(b, true) <= p.y).toBe(true)
      }
    }
  })

  it("fits every card into the viewport and keeps the cursor's world point when zooming", () => {
    const { positions2 } = arrange(deliveryGraph, true)
    const camera = fit2(deliveryGraph, positions2, true, 900, 500)
    for (const node of deliveryGraph.nodes) {
      const p = positions2[node.id]!
      expect(p.x * camera.zoom + camera.x).toBeGreaterThanOrEqual(31)
      expect((p.x + CARD_WIDTH) * camera.zoom + camera.x).toBeLessThanOrEqual(869)
      expect((p.y + nodeHeight(node, true)) * camera.zoom + camera.y).toBeLessThanOrEqual(469)
    }
    const cursor = { x: 237, y: 181 }
    const next = zoomAt(camera, 1.5, cursor)
    expect((cursor.x - camera.x) / camera.zoom).toBeCloseTo((cursor.x - next.x) / next.zoom)
    expect((cursor.y - camera.y) / camera.zoom).toBeCloseTo((cursor.y - next.y) / next.zoom)
  })

  it("gives parallel and self edges separate paths while preserving port anchors", () => {
    const jobs = deliveryGraph.edges[0]!
    const retry = deliveryGraph.edges[2]!
    const graph = { ...deliveryGraph, edges: [jobs, { ...jobs, id: "jobs2" }, retry, { ...retry, id: "retry2" }] }
    const positions = { api: { x: 0, y: 0 }, worker: { x: 500, y: 0 }, monitor: { x: 1000, y: 0 } }
    const paths = edgePaths(graph, positions, true)
    expect(new Set(paths.map((item) => item.path)).size).toBe(4)
    expect(paths[0]!.path).toMatch(new RegExp(`^M ${CARD_WIDTH} ${HEADER_HEIGHT + ROW_HEIGHT / 2} `))
    expect(edgePaths(graph, positions, false)[0]!.path).toMatch(new RegExp(`^M ${CARD_WIDTH} ${HEADER_HEIGHT / 2} `))
  })
})
