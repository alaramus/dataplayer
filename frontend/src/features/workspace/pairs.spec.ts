import { describe, expect, it } from "vitest"

import type { PasteOffer } from "@/client"

import type { CatalogSide } from "./catalogSides"
import {
  dropOnPair,
  itemDetail,
  pairIntact,
  pairCommand,
  pairTitle,
  pasteIntentFor,
  swapped,
  usable,
} from "./pairs"

const files = { panelId: "catalog:f", connectorId: "f", title: "Files" }
const copyOfFiles = { panelId: "catalog:f:copy:1", connectorId: "f", title: "Files" }
const database = { panelId: "catalog:d", connectorId: "d", title: "Postgres" }

describe("offering a catalog to Pair", () => {
  it("waits for the second, and a repeated drop only waits again", () => {
    expect(dropOnPair(null, files)).toEqual({ kind: "hold" })
    expect(dropOnPair(files, files)).toEqual({ kind: "hold" })
  })

  it("opens the pair with the waiting one on the left", () => {
    expect(dropOnPair(files, database)).toEqual({ kind: "complete", left: files, right: database })
  })

  it("refuses a second catalog of the waiting connection", () => {
    expect(dropOnPair(files, copyOfFiles)).toEqual({
      kind: "refuse",
      reason: "a catalog of this connection is already waiting",
    })
  })

  it("says on the command what pressing it would do, and refuses where it would", () => {
    expect(pairCommand(null, files)).toEqual({ tooltip: "Pair with another connection", refused: false })
    expect(pairCommand(files, database)).toEqual({ tooltip: "Pair with Files", refused: false })
    expect(pairCommand(files, copyOfFiles)).toEqual({
      tooltip: "Pair with another connection — a catalog of this connection is already waiting",
      refused: true,
    })
  })
})

describe("an open pair", () => {
  const pair = { id: "pair-1", left: files, right: database }

  it("is named by both connections, left first", () => {
    expect(pairTitle(pair)).toBe("Files and Postgres")
    expect(pairTitle(swapped(pair))).toBe("Postgres and Files")
  })

  it("is intact only while both catalogs are torn off into it", () => {
    expect(pairIntact(pair, new Set(["catalog:f", "catalog:d"]))).toBe(true)
    expect(pairIntact(pair, new Set(["catalog:f"]))).toBe(false)
  })
})

describe("an item of the bar", () => {
  const left: CatalogSide = {
    connectorId: "f",
    place: "reports",
    placeLabel: "reports",
    ticked: ["reports/q3.csv"],
    tickedLabel: "q3.csv",
    searchFrom: "reports",
  }
  const right: CatalogSide = {
    connectorId: "d",
    place: "demo_lab",
    placeLabel: "demo_lab",
    ticked: ["demo_lab.orders"],
    tickedLabel: "orders",
    searchFrom: null,
  }
  const creating: PasteOffer = {
    kind: "rows_new_relation",
    title: "Create a table",
    available: true,
    workflow: "new-relation",
  }
  const adding: PasteOffer = { ...creating, kind: "rows_into_relation", workflow: "into-relation" }

  it("runs the Paste that would be made in the other catalog", () => {
    expect(pasteIntentFor(creating, left, right)).toEqual({
      sourceConnectorId: "f",
      sourceNodeIds: ["reports/q3.csv"],
      sourceLabel: "q3.csv",
      mode: "copy",
      destinationConnectorId: "d",
      destinationNodeId: "demo_lab",
      destinationLabel: "demo_lab",
      targetNodeId: "demo_lab.orders",
      targetLabel: "orders",
      offers: [creating],
    })
  })

  it("takes a target only when exactly one node is ticked there", () => {
    const two = { ...right, ticked: ["demo_lab.orders", "demo_lab.projects"], tickedLabel: "2 items" }

    expect(pasteIntentFor(adding, left, two).targetNodeId).toBeNull()
  })

  it("runs a move as a move", () => {
    const moving: PasteOffer = { kind: "file_move", title: "Move files", mode: "move", available: true }

    expect(pasteIntentFor(moving, left, right).mode).toBe("move")
  })

  it("says what goes where, or why it cannot", () => {
    expect(itemDetail(creating, pasteIntentFor(creating, left, right))).toBe("q3.csv into demo_lab")
    expect(itemDetail(adding, pasteIntentFor(adding, left, right))).toBe("q3.csv into orders")
    const off = { ...creating, available: false, reason: "Tick a file or a table readable as rows" }
    expect(usable(off)).toBe(false)
    expect(itemDetail(off, pasteIntentFor(off, left, right))).toBe("Tick a file or a table readable as rows")
  })
})
