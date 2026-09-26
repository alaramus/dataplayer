import { describe, expect, it } from "vitest"

import type { Card } from "@/client"
import { ICONS } from "@/features/catalog/nodes"
import { CARD_WIDTH, HEADER_HEIGHT } from "@/shared/graph/layout"
import { graphProblem } from "@/shared/graph/model"

import {
  cardProblem,
  checkedRowsKey,
  dropSpot,
  freeSpot,
  movedCard,
  newPipelineName,
  pipelineGraph,
  positionsOf,
  rowId,
  TOP_ICON,
  withoutCard,
  withRows,
  worldPoint,
} from "./model"
import type { CardConnection } from "./model"

const orders: Card = {
  id: "card-1",
  connector_id: "db",
  connector_name: "Sales (old name)",
  x: 40,
  y: 60,
  rows: [
    { node_id: "sales.orders", label: "orders", kind: "table", trail: ["sales"] },
    { node_id: "public", label: "public", kind: "schema", trail: [] },
  ],
}
const files: Card = {
  id: "card-2",
  connector_id: "files",
  connector_name: "Files",
  x: 500,
  y: 60,
  rows: [
    { node_id: null, label: "Files", kind: null, trail: [] },
    { node_id: "reports", label: "reports", kind: "directory", trail: [] },
  ],
}
const connections = new Map<string, CardConnection>([
  ["db", { name: "Sales", adapterType: "postgres", enabled: true }],
  ["files", { name: "Files", adapterType: "file", enabled: true }],
])
const titles = new Map([["postgres", "PostgreSQL"], ["file", "Personal storage"]])

describe("a pipeline's cards on the canvas", () => {
  it("draws a card a connection, with a row per ticked node and where it lives", () => {
    const graph = pipelineGraph([orders, files], connections, new Map(), titles)

    expect(graphProblem(graph)).toBeNull()
    const [sales, storage] = graph.nodes
    expect(sales).toMatchObject({ id: "card-1", label: "Sales", caption: "PostgreSQL", groupId: "db", placeholder: false })
    expect(sales?.rows).toEqual([
      { id: "node:sales.orders", label: "orders", detail: "sales", icon: ICONS.table, muted: false },
      { id: "node:public", label: "public", detail: "schema", icon: ICONS.schema, muted: false },
    ])
    expect(storage?.rows[0]).toEqual({ id: "top", label: "Files", detail: "top", icon: TOP_ICON, muted: false })
    expect(storage?.rows[1]?.detail).toBe("folder")
  })

  it("marks a row the source no longer has, and a card whose connection cannot be read", () => {
    const states = new Map([
      ["card-1", { problem: null, missing: ["sales.orders"], checked: true }],
      ["card-2", { problem: "Connection refused", missing: [], checked: false }],
    ])

    const [sales, storage] = pipelineGraph([orders, files], connections, states, titles).nodes

    expect(sales?.rows[0]).toMatchObject({ muted: true, detail: "not found" })
    expect(sales?.rows[1]?.muted).toBe(false)
    expect(storage).toMatchObject({ caption: "Connection refused", placeholder: true })
  })

  it("says why a card cannot be worked with before the server has been asked", () => {
    expect(cardProblem(undefined, undefined)).toBe("This connection is gone, or no longer shared with you")
    expect(cardProblem({ name: "Sales", adapterType: "postgres", enabled: false }, undefined)).toBe(
      "This connection is switched off"
    )
    expect(cardProblem(connections.get("db"), undefined)).toBeNull()

    const gone = pipelineGraph([orders], new Map(), new Map(), titles).nodes[0]
    expect(gone).toMatchObject({ label: "Sales (old name)", placeholder: true })
  })

  it("keeps a node's id apart from the top of a connection", () => {
    expect(rowId(null)).toBe("top")
    expect(rowId(undefined)).toBe("top")
    expect(rowId("top")).toBe("node:top")
    expect(checkedRowsKey(files)).toBe("top\u0000node:reports")
  })
})

describe("placing and changing cards", () => {
  it("turns a point of the screen into one of the canvas, and centres a drop under it", () => {
    expect(worldPoint({ x: 100, y: 50, zoom: 2 }, { x: 300, y: 250 })).toEqual({ x: 100, y: 100 })
    expect(dropSpot({ x: 400, y: 300 })).toEqual({ x: 400 - CARD_WIDTH / 2, y: 300 - HEADER_HEIGHT / 2 })
  })

  it("places a pressed card at the nearest spot where it covers no other card", () => {
    // Orders is two rows tall: a card of one row goes as near as clears it,
    // below it rather than as far above.
    const below = freeSpot([orders], { x: 40, y: 60 }, 1)
    expect(below).toEqual({ x: 40, y: 60 + 2 * (HEADER_HEIGHT + 48) })
    // Nothing there: exactly where it was asked.
    expect(freeSpot([orders], { x: 1000, y: 60 }, 3)).toEqual({ x: 1000, y: 60 })
    // Every spot it tries is clear of both cards by the gap.
    const crowded = [orders, { ...files, x: 40, y: below.y }]
    const spot = freeSpot(crowded, { x: 40, y: 60 }, 1)
    for (const card of crowded) {
      const apart = spot.x >= card.x + CARD_WIDTH + 48 || card.x >= spot.x + CARD_WIDTH + 48 ||
        spot.y >= card.y + HEADER_HEIGHT + card.rows.length * 24 + 48 || card.y >= spot.y + HEADER_HEIGHT + 24 + 48
      expect(apart).toBe(true)
    }
  })

  it("moves, changes and removes one card and leaves the others", () => {
    const cards = [orders, files]

    expect(positionsOf(movedCard(cards, "card-2", { x: 10.4, y: 20.6 }))).toEqual({
      "card-1": { x: 40, y: 60 },
      "card-2": { x: 10, y: 21 },
    })
    expect(withRows(cards, "card-1", files.rows)[0]?.rows).toBe(files.rows)
    expect(withRows(cards, "card-1", files.rows)[1]).toBe(files)
    expect(withoutCard(cards, "card-1")).toEqual([files])
  })

  it("names a new pipeline as a new dashboard is named", () => {
    expect(newPipelineName(0)).toBe("My pipeline")
    expect(newPipelineName(2)).toBe("Pipeline 3")
  })
})
