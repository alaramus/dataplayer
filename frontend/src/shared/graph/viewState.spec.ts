import { describe, expect, it } from "vitest"

import { emptyGraphView, parseGraphView, serializeGraphView } from "./viewState"

describe("saved graph views", () => {
  it("round trips independent layouts and cameras, with no source metadata", () => {
    const state = { ...emptyGraphView(), mode: "3d" as const, positions2: { task: { x: 30, y: -20 } }, positions3: { task: { x: 30, y: 80, z: -40 } }, camera2: { x: 10, y: 20, zoom: 0.5 }, camera3: { position: { x: 10, y: 20, z: 100 }, target: { x: 0, y: 0, z: 0 } }, expanded: false, groupId: "delivery" }
    expect(parseGraphView(serializeGraphView(state))).toEqual(state)
    expect(JSON.parse(serializeGraphView({ ...state, graph: { secret: "metadata" } } as typeof state)).state).not.toHaveProperty("graph")
  })

  it("reflows old 3D positions while retaining the 2D layout and view options", () => {
    const oldState = {
      layout3dVersion: 2,
      mode: "3d" as const,
      positions2: { task: { x: 30, y: -20 } },
      positions3: { task: { x: 30, y: 80, z: -40 } },
      camera2: { x: 10, y: 20, zoom: 0.5 },
      camera3: { position: { x: 10, y: 20, z: 100 }, target: { x: 0, y: 0, z: 0 } },
      expanded: false,
      labels: false,
      groupId: "delivery",
    }

    const restored = parseGraphView(JSON.stringify({ version: 1, state: oldState }))

    expect(restored).toMatchObject({
      mode: "3d",
      positions2: oldState.positions2,
      positions3: {},
      camera3: null,
      labels: false,
      layout3dVersion: 3,
    })
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
