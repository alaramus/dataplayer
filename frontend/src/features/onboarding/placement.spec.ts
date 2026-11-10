import { describe, expect, it } from "vitest"

import { EDGE, GAP, placeHint } from "./placement"

const viewport = { width: 1200, height: 800 }
const card = { width: 320, height: 120 }

describe("placeHint", () => {
  it("stands to the right of a control near the left edge", () => {
    const spot = placeHint({ top: 300, left: 40, width: 40, height: 40 }, card, viewport)
    expect(spot.left).toBe(40 + 40 + GAP)
    expect(spot.top).toBe(300 + 20 - 60)
  })

  it("goes to the left where the right has no room", () => {
    const spot = placeHint({ top: 300, left: 1100, width: 60, height: 40 }, card, viewport)
    expect(spot.left).toBe(1100 - GAP - 320)
  })

  it("goes below a control as wide as the window", () => {
    const spot = placeHint({ top: 100, left: 20, width: 1160, height: 40 }, card, viewport)
    expect(spot.top).toBe(100 + 40 + GAP)
  })

  it("keeps clear of the window's top edge", () => {
    const spot = placeHint({ top: 0, left: 40, width: 40, height: 40 }, card, viewport)
    expect(spot.top).toBe(EDGE)
  })

  it("sits inside the lower right corner of a control larger than every side", () => {
    const spot = placeHint({ top: 0, left: 0, width: 1200, height: 800 }, card, viewport)
    expect(spot).toEqual({ top: 800 - EDGE - 120, left: 1200 - EDGE - 320 })
  })

  it("waits in the lower right of the window with nothing to ring", () => {
    expect(placeHint(null, card, viewport)).toEqual({ top: 800 - EDGE - 120, left: 1200 - EDGE - 320 })
  })
})
