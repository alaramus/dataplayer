import { describe, expect, it } from "vitest"

import { panelColorStyle } from "./panelColor"

describe("custom panel colors", () => {
  it.each([
    ["#000000", "#ffffff", "rgba(0, 0, 0, 0.28)"],
    ["#ffffff", "#000000", "rgba(255, 255, 255, 0.28)"],
    ["#0000FF", "#ffffff", "rgba(0, 0, 255, 0.28)"],
    ["#ff0000", "#000000", "rgba(255, 0, 0, 0.28)"],
    ["#00ff00", "#000000", "rgba(0, 255, 0, 0.28)"],
    ["#777777", "#000000", "rgba(119, 119, 119, 0.28)"],
  ])("keeps text readable on %s", (background, foreground, quiet) => {
    expect(panelColorStyle(background)).toEqual({
      "--dp-panel-background": background,
      "--dp-panel-foreground": foreground,
      "--dp-panel-quiet": quiet,
    })
  })

  it.each([null, undefined, "", "red", "#123", "#12345678", "#123456\n", "url(example)"])(
    "leaves the theme in control for %s", (color) => {
      expect(panelColorStyle(color)).toEqual({})
    }
  )
})
