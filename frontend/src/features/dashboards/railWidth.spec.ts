import { describe, expect, it } from "vitest"

import { clampRailWidth, parseRailWidth, RAIL_DEFAULT_PX, RAIL_MIN_PX } from "./railWidth"

describe("the width of the dashboards rail", () => {
  it("keeps a width that fits", () => {
    expect(clampRailWidth(320, 1600)).toBe(320)
  })

  it("stays under two fifths of the space however far it is dragged", () => {
    expect(clampRailWidth(1200, 1600)).toBe(640)
  })

  it("stays wide enough for its own buttons", () => {
    expect(clampRailWidth(40, 1600)).toBe(RAIL_MIN_PX)
  })

  it("keeps its floor on a window too narrow for both", () => {
    expect(clampRailWidth(300, 400)).toBe(RAIL_MIN_PX)
  })

  it("reads back what was stored, and the default for anything else", () => {
    expect(parseRailWidth("412")).toBe(412)
    expect(parseRailWidth(null)).toBe(RAIL_DEFAULT_PX)
    expect(parseRailWidth("wide")).toBe(RAIL_DEFAULT_PX)
    expect(parseRailWidth("-5")).toBe(RAIL_DEFAULT_PX)
  })
})
