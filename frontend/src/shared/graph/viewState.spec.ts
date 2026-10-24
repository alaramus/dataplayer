import { describe, expect, it } from "vitest"

import { emptyGraphView, parseGraphView, serializeGraphView } from "./viewState"

describe("saved graph views", () => {
  it("round trips independent layouts and cameras, with no source metadata", () => {
    const state = { ...emptyGraphView(), mode: "3d" as const, positions2: { task: { x: 30, y: -20 } }, positions3: { task: { x: 30, y: 80, z: -40 } }, camera2: { x: 10, y: 20, zoom: 0.5 }, camera3: { position: { x: 10, y: 20, z: 100 }, target: { x: 0, y: 0, z: 0 } }, expanded: false, groupId: "delivery" }
    expect(parseGraphView(serializeGraphView(state))).toEqual(state)
    expect(JSON.parse(serializeGraphView({ ...state, graph: { secret: "metadata" } } as typeof state)).state).not.toHaveProperty("graph")
  })

  it("keeps the 3D layout of a view saved with a layout revision", () => {
    const state = { ...emptyGraphView(), mode: "3d" as const, positions3: { task: { x: 30, y: 80, z: -40 } }, camera3: { position: { x: 10, y: 20, z: 100 }, target: { x: 0, y: 0, z: 0 } } }
    expect(parseGraphView(JSON.stringify({ version: 1, state: { ...state, layout3dVersion: 3 } }))).toEqual(state)
  })

  it.each([null, "", "{", '{"version":99}', " ".repeat(200_001)])("ignores an absent, corrupt or unsupported value", (raw) => {
    expect(parseGraphView(raw)).toBeNull()
  })

  it("rejects non-finite positions, unsafe zoom and a camera inside its own target", () => {
    expect(() => serializeGraphView({ ...emptyGraphView(), positions2: { a: { x: Infinity, y: 0 } } })).toThrow()
    for (const camera2 of [{ x: 0, y: 0, zoom: 0 }, { x: 0, y: 0, zoom: 4 }]) {
      expect(parseGraphView(JSON.stringify({ version: 1, state: { ...emptyGraphView(), camera2 } }))).toBeNull()
    }
    const point = { x: 0, y: 0, z: 0 }
    expect(parseGraphView(JSON.stringify({ version: 1, state: { ...emptyGraphView(), camera3: { position: point, target: point } } }))).toBeNull()
  })
})
