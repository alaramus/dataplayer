import { describe, expect, it } from "vitest"

import { deliveryGraph } from "./fixtures"
import {
  along, arrange, CARD_WIDTH, edgePaths, fit2, HEADER_HEIGHT, labelSpots, nodeHeight, portAnchors, ROW_HEIGHT, zoomAt,
} from "./layout"
import type { Curve } from "./layout"

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

  it("anchors only the ports an edge reaches, on the side the curve leaves by", () => {
    const positions = { api: { x: 0, y: 0 }, worker: { x: 500, y: 0 }, monitor: { x: 1000, y: 0 } }
    const anchors = portAnchors(edgePaths(deliveryGraph, positions, true))

    // The worker is to the right of the gateway and holds a self reference,
    // so one of its fields is reached from both sides at once.
    expect(anchors.get("api")?.get("events")).toEqual({ left: false, right: true })
    expect(anchors.get("worker")?.get("input")).toEqual({ left: true, right: true })
    // Nothing else is anchored: the gateway's third field is named by no edge,
    // and the connection to the monitor names no port on it at all.
    expect([...anchors].map(([id, ports]) => [id, [...ports.keys()].sort()])).toEqual([
      ["api", ["events", "metrics"]],
      ["worker", ["input", "retry"]],
    ])

    // Which side is geometry, not a property of the field: the same document
    // laid out the other way round anchors the same port on the other side.
    const mirrored = portAnchors(
      edgePaths(deliveryGraph, { ...positions, api: { x: 500, y: 0 }, worker: { x: 0, y: 0 } }, true)
    )
    expect(mirrored.get("api")?.get("events")).toEqual({ left: true, right: false })
  })

  it("writes a label that would cover another further along its own line", () => {
    // From one row to two rows a step apart: the middles all but meet.
    const first: Curve = [{ x: 0, y: 0 }, { x: 150, y: 0 }, { x: 250, y: 100 }, { x: 400, y: 100 }]
    const second: Curve = [{ x: 0, y: 0 }, { x: 150, y: 0 }, { x: 250, y: 110 }, { x: 400, y: 110 }]
    const spots = labelSpots([
      { id: "a", text: "1 · Save as CSV", curve: first },
      { id: "b", text: "2 · Save as CSV", curve: second },
    ])
    expect(spots.get("a")).toEqual(along(first, 0.5))
    const moved = spots.get("b")!
    expect(moved).not.toEqual(along(second, 0.5))
    expect(Math.abs(moved.y - spots.get("a")!.y) >= 16 || Math.abs(moved.x - spots.get("a")!.x) >= 15 * 6.5).toBe(true)
    // Alone, a label keeps the middle.
    expect(labelSpots([{ id: "b", text: "2 · Save as CSV", curve: second }]).get("b")).toEqual(along(second, 0.5))
    // Two cards close together leave no clear point along the line: stacked.
    const short: Curve = [{ x: 0, y: 0 }, { x: 45, y: 0 }, { x: 75, y: 10 }, { x: 120, y: 10 }]
    const close = labelSpots([
      { id: "a", text: "1 · Save as CSV", curve: short },
      { id: "b", text: "2 · Save as CSV", curve: short },
    ])
    expect(close.get("b")).toEqual({ x: along(short, 0.5).x, y: along(short, 0.5).y + 16 })
  })
})
