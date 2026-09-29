import { describe, expect, it } from "vitest"

import { at, first } from "@/shared/testing/collections"

import { bringToFront, CASCADE_STEP, clamp, fit, GRAB_MARGIN, place, resize } from "./geometry"
import type { Rect } from "./geometry"

const VIEWPORT = { width: 1280, height: 800 }
const SIZE = { width: 520, height: 480 }

describe("placing a new window", () => {
  it("opens the first one in the middle, clear of what is behind it", () => {
    // Not the corner: a window there covers the column it was opened from,
    // including the control that opens the next one.
    const rect = place(SIZE, null, VIEWPORT)

    expect(rect.width).toBe(SIZE.width)
    expect(rect.x).toBe((VIEWPORT.width - SIZE.width) / 2)
    expect(rect.y).toBe((VIEWPORT.height - SIZE.height) / 2)
  })

  it("offsets the next one so both stay readable", () => {
    const before = place(SIZE, null, VIEWPORT)
    const after = place(SIZE, before, VIEWPORT)

    expect(after.x).toBe(before.x + CASCADE_STEP)
    expect(after.y).toBe(before.y + CASCADE_STEP)
  })

  it("measures from the last window opened, not from how many are open", () => {
    // Closing a window in the middle must not send the next one backwards
    // onto a place that is already taken.
    const opened = place(SIZE, null, VIEWPORT)
    const second = place(SIZE, opened, VIEWPORT)
    const third = place(SIZE, second, VIEWPORT)

    expect(third.x).toBe(opened.x + 2 * CASCADE_STEP)
  })

  it("starts the cascade over rather than walking off the screen", () => {
    let rect = place(SIZE, null, VIEWPORT)
    for (let step = 0; step < 40; step += 1) rect = place(SIZE, rect, VIEWPORT)

    expect(rect.x + GRAB_MARGIN).toBeLessThanOrEqual(VIEWPORT.width)
    expect(rect.y + GRAB_MARGIN).toBeLessThanOrEqual(VIEWPORT.height)
  })

  // A Guide of 680px opened from a window cascaded its foot off a 720px
  // screen, out of reach of its own resize handle (D187).
  it("lifts the next one rather than put its foot off screen", () => {
    const tall = { width: 720, height: 680 }
    const viewport = { width: 1280, height: 720 }
    const first = place(tall, null, viewport)
    const rect = place(tall, first, viewport)

    expect(rect.y + rect.height).toBeLessThanOrEqual(viewport.height)
    // Lifted, not started over: laid exactly on the first, the second hid it.
    expect(rect).not.toEqual(first)
  })

  it("shrinks a window that cannot fit the viewport", () => {
    const rect = place({ width: 900, height: 900 }, null, { width: 400, height: 300 })

    expect(rect.width).toBeLessThanOrEqual(400)
    expect(rect.height).toBeLessThanOrEqual(300)
  })
})

describe("keeping a window reachable", () => {
  const dragged = (x: number, y: number): Rect => ({ x, y, ...SIZE })

  it("leaves a window that is already inside alone", () => {
    const rect = dragged(100, 100)

    expect(clamp(rect, VIEWPORT)).toEqual(rect)
  })

  it("keeps a grab strip on screen when dragged off the right", () => {
    const rect = clamp(dragged(5000, 100), VIEWPORT)

    expect(rect.x).toBeLessThanOrEqual(VIEWPORT.width - GRAB_MARGIN)
  })

  it("keeps a grab strip on screen when dragged off the bottom", () => {
    const rect = clamp(dragged(100, 5000), VIEWPORT)

    expect(rect.y).toBeLessThanOrEqual(VIEWPORT.height - GRAB_MARGIN)
  })

  it("never lets the title bar go above the top edge", () => {
    // Off the top is the one direction that cannot be undone: the bar the
    // user drags by would be the part that left.
    expect(clamp(dragged(100, -400), VIEWPORT).y).toBe(0)
  })

  it("keeps a grab strip on screen when dragged off the left", () => {
    const rect = clamp(dragged(-5000, 100), VIEWPORT)

    expect(rect.x + rect.width).toBeGreaterThanOrEqual(GRAB_MARGIN)
  })

  it("pulls windows back when the viewport shrinks under them", () => {
    const rect = clamp(dragged(1000, 700), { width: 640, height: 480 })

    expect(rect.x).toBeLessThanOrEqual(640 - GRAB_MARGIN)
    expect(rect.y).toBeLessThanOrEqual(480 - GRAB_MARGIN)
  })
})

describe("sizing a window", () => {
  it("fits its opening height to the content within the viewport", () => {
    const rect = fit(
      { x: 300, y: 200, width: 560, height: 660 },
      { width: 560, height: 280 },
      VIEWPORT
    )

    expect(rect.height).toBe(280)
    expect(rect.x).toBe(300)
    expect(rect.y).toBe(390)
  })

  it("does not fit beyond the viewport", () => {
    const rect = fit(
      { x: 0, y: 0, width: 400, height: 300 },
      { width: 2000, height: 2000 },
      VIEWPORT
    )

    expect(rect.width).toBe(VIEWPORT.width)
    expect(rect.height).toBe(VIEWPORT.height)
  })

  it("resizes from an edge without crossing the minimum", () => {
    const rect = resize(
      { x: 100, y: 100, width: 500, height: 400 },
      "left",
      { x: 580, y: 100 },
      VIEWPORT,
      { width: 280, height: 180 }
    )

    expect(rect.width).toBe(280)
    expect(rect.x).toBe(320)
  })

  it("resizes a corner and keeps it inside the viewport", () => {
    const rect = resize(
      { x: 100, y: 100, width: 500, height: 400 },
      "bottom-right",
      { x: 5000, y: 5000 },
      VIEWPORT,
      { width: 280, height: 180 }
    )

    expect(rect.x + rect.width).toBe(VIEWPORT.width)
    expect(rect.y + rect.height).toBe(VIEWPORT.height)
  })
})

describe("the order windows stack in", () => {
  it("moves the named one to the end, which is the front", () => {
    expect(bringToFront(["a", "b", "c"], "b")).toEqual(["a", "c", "b"])
  })

  it("leaves the order alone when the front one is asked for again", () => {
    expect(bringToFront(["a", "b", "c"], "c")).toEqual(["a", "b", "c"])
  })

  it("ignores a window that is not there", () => {
    expect(bringToFront(["a", "b"], "zzz")).toEqual(["a", "b"])
  })

  it("is a position, so there is no number to overflow", () => {
    // The old engine incremented a z-index counter for ever. Here the order
    // is the list, so opening and focusing a thousand times changes nothing
    // but the sequence.
    let order = ["a", "b", "c"]
    for (let step = 0; step < 1000; step += 1) {
      order = bringToFront(order, step % 2 === 0 ? "a" : "b")
    }

    expect([...order].sort()).toEqual(["a", "b", "c"])
    expect(at(order, 2)).toBe("b")
    expect(first(order)).toBe("c")
  })
})
