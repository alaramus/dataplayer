import { describe, expect, it } from "vitest"

import { panelColorStyle } from "./panelColor"

describe("custom panel colors", () => {
  it.each([
    ["#000000", "#ffffff"],
    ["#ffffff", "#000000"],
    ["#0000FF", "#ffffff"],
    ["#ff0000", "#000000"],
    ["#00ff00", "#000000"],
    ["#777777", "#000000"],
  ])("keeps text readable on %s", (background, foreground) => {
    expect(panelColorStyle(background)).toEqual({
      "--dp-panel-background": background,
      "--dp-panel-foreground": foreground,
    })
  })

  it.each([null, undefined, "", "red", "#123", "#12345678", "#123456\n", "url(example)"])(
    "leaves the theme in control for %s", (color) => {
      expect(panelColorStyle(color)).toEqual({})
    }
  )
})
