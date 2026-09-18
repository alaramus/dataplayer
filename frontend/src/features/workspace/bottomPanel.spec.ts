import { describe, expect, it } from "vitest"

import {
  BOTTOM_PANEL_DEFAULT_HEIGHT,
  BOTTOM_PANEL_MIN_HEIGHT,
  clampBottomPanelHeight,
  readBottomPanel,
  toggleTool,
} from "./bottomPanel"

const TOOLS = ["services", "terminal"]

describe("what a stored bottom panel comes to", () => {
  it("is hidden at the default height when nothing was stored", () => {
    expect(readBottomPanel(null, TOOLS)).toEqual({ open: null, height: BOTTOM_PANEL_DEFAULT_HEIGHT })
  })

  it("comes back as it was left", () => {
    expect(readBottomPanel(JSON.stringify({ open: "services", height: 340 }), TOOLS)).toEqual({
      open: "services",
      height: 340,
    })
  })

  it("forgets a tool that is not one any more, and keeps the height", () => {
    expect(readBottomPanel(JSON.stringify({ open: "gone", height: 340 }), TOOLS)).toEqual({
      open: null,
      height: 340,
    })
  })

  it("takes the default for anything it cannot read", () => {
    for (const raw of ["not json", "[]", "7", JSON.stringify({ open: 3, height: "tall" })]) {
      expect(readBottomPanel(raw, TOOLS)).toEqual({ open: null, height: BOTTOM_PANEL_DEFAULT_HEIGHT })
    }
  })

  it("never comes back shorter than the floor", () => {
    expect(readBottomPanel(JSON.stringify({ open: null, height: 4 }), TOOLS).height).toBe(
      BOTTOM_PANEL_MIN_HEIGHT
    )
  })
})

describe("the button of a tool", () => {
  it("shows its tool, replacing another one", () => {
    expect(toggleTool({ open: null, height: 200 }, "services")).toEqual({ open: "services", height: 200 })
    expect(toggleTool({ open: "terminal", height: 200 }, "services").open).toBe("services")
  })

  it("hides the panel when its tool is the one shown", () => {
    expect(toggleTool({ open: "services", height: 200 }, "services")).toEqual({ open: null, height: 200 })
  })
})

describe("the height of the panel", () => {
  it("has a floor and whole pixels", () => {
    expect(clampBottomPanelHeight(10)).toBe(BOTTOM_PANEL_MIN_HEIGHT)
    expect(clampBottomPanelHeight(301.6)).toBe(302)
  })
})
