import { describe, expect, it } from "vitest"

import { clampBox, compact, findFreeSpot, gridRows, moveItem, overlaps, resizeItem } from "./gridLayout"
import type { Placed } from "./gridLayout"

function item(id: string, x: number, y: number, w = 6, h = 5): Placed {
  return { id, layout: { x, y, w, h } }
}

function noOverlaps(items: Placed[]): boolean {
  return items.every((a, i) => items.slice(i + 1).every((b) => !overlaps(a.layout, b.layout)))
}

describe("the dashboard grid", () => {
  it("keeps a box inside the columns and the size limits", () => {
    expect(clampBox({ x: 10, y: -3, w: 6, h: 1 })).toEqual({ x: 6, y: 0, w: 6, h: 2 })
    expect(clampBox({ x: 0, y: 0, w: 40, h: 99 })).toEqual({ x: 0, y: 0, w: 12, h: 40 })
  })

  it("lets everything fall up as far as it can", () => {
    const items = [item("a", 0, 7), item("b", 6, 12)]

    expect(compact(items)).toEqual([item("a", 0, 0), item("b", 6, 0)])
  })

  it("keeps the order it was given", () => {
    const items = [item("low", 0, 10), item("high", 6, 0)]

    expect(compact(items).map((one) => one.id)).toEqual(["low", "high"])
  })

  it("pushes what a moved widget lands on down, then settles", () => {
    const items = [item("a", 0, 0), item("b", 6, 0), item("c", 0, 5)]

    const moved = moveItem(items, "c", { x: 6, y: 0 })

    expect(noOverlaps(moved)).toBe(true)
    expect(moved.find((one) => one.id === "c")?.layout).toEqual({ x: 6, y: 0, w: 6, h: 5 })
    expect(moved.find((one) => one.id === "b")?.layout).toEqual({ x: 6, y: 5, w: 6, h: 5 })
  })

  it("makes room when a widget grows", () => {
    const items = [item("a", 0, 0), item("b", 0, 5)]

    const grown = resizeItem(items, "a", { w: 6, h: 8 })

    expect(noOverlaps(grown)).toBe(true)
    expect(grown.find((one) => one.id === "b")?.layout.y).toBe(8)
  })

  it("finds the first place a new widget fits, reading order", () => {
    const items = [item("a", 0, 0), item("b", 0, 5, 12)]

    expect(findFreeSpot(items, 6, 5)).toEqual({ x: 6, y: 0 })
    expect(findFreeSpot(items, 12, 5)).toEqual({ x: 0, y: 10 })
    expect(findFreeSpot([], 3, 5)).toEqual({ x: 0, y: 0 })
  })

  it("counts the rows the widgets take", () => {
    expect(gridRows([item("a", 0, 0), item("b", 6, 3, 6, 9)])).toBe(12)
    expect(gridRows([])).toBe(0)
  })
})
