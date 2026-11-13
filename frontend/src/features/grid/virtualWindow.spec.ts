import { describe, expect, it } from "vitest"

import { columnWindow, revealOffset, rowWindow } from "./virtualWindow"

describe("the rows drawn", () => {
  it("covers what shows and at least the overscan beyond it", () => {
    // 500 rows of 25px, scrolled to row 200, 20 rows in view.
    const window = rowWindow(500, 25, 200 * 25, 20 * 25, 10)
    expect(window.start).toBeLessThanOrEqual(190)
    expect(window.end).toBeGreaterThanOrEqual(230)
    expect(window.before).toBe(window.start * 25)
    expect(window.after).toBe((500 - window.end) * 25)
  })

  it("stays put while the scroll moves within a step", () => {
    const at = (row: number) => rowWindow(500, 25, row * 25, 500, 10)
    expect(at(201)).toEqual(at(209))
    expect(at(209)).not.toEqual(at(211))
  })

  it("stops at both ends of the page", () => {
    expect(rowWindow(500, 25, 0, 500, 10).start).toBe(0)
    const end = rowWindow(500, 25, 499 * 25, 500, 10)
    expect(end.end).toBe(500)
    expect(end.after).toBe(0)
    expect(rowWindow(5, 25, 0, 1000, 10)).toEqual({ start: 0, end: 5, before: 0, after: 0 })
    expect(rowWindow(0, 25, 0, 1000, 10)).toEqual({ start: 0, end: 0, before: 0, after: 0 })
  })
})

describe("the columns drawn", () => {
  const widths = Array.from({ length: 300 }, (_, index) => 100 + (index % 3) * 50)
  const total = widths.reduce((sum, width) => sum + width, 0)

  it("covers the columns that cross the view, with room standing in for the rest", () => {
    const window = columnWindow(widths, 10_000, 600, 3)
    let position = 0
    const crossing: number[] = []
    widths.forEach((width, index) => {
      if (position + width > 10_000 && position < 10_600) crossing.push(index)
      position += width
    })
    expect(window.start).toBeLessThanOrEqual(crossing[0]! - 3)
    expect(window.end).toBeGreaterThanOrEqual(crossing.at(-1)! + 1 + 3)
    const drawn = widths.slice(window.start, window.end).reduce((sum, width) => sum + width, 0)
    expect(window.before + drawn + window.after).toBe(total)
  })

  it("draws everything when everything fits", () => {
    expect(columnWindow([100, 120], 0, 2000, 3)).toEqual({ start: 0, end: 2, before: 0, after: 0 })
  })

  it("ends at the last column when scrolled to it", () => {
    const window = columnWindow(widths, total - 500, 500, 3)
    expect(window.end).toBe(300)
    expect(window.after).toBe(0)
  })
})

describe("revealing a cell", () => {
  it("leaves the scroll alone when the cell shows", () => {
    expect(revealOffset(100, 500, 30, 200, 25)).toBe(100)
  })

  it("brings a cell under the stuck heading out from under it", () => {
    // Heading 30px tall; the row starts at 110 and the box is scrolled to 100.
    expect(revealOffset(100, 500, 30, 110, 25)).toBe(80)
  })

  it("scrolls just far enough to show a cell past the far edge", () => {
    expect(revealOffset(0, 500, 30, 600, 25)).toBe(125)
  })
})
