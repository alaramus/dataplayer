import { describe, expect, it } from "vitest"

import bundledIcons from "@quasar/extras/material-icons/icons.json"

import { appIcons } from "./icons"

describe("shared semantic icons", () => {
  it("uses glyphs available in the installed Material Icons font", () => {
    const bundled = new Set(bundledIcons)
    for (const icon of Object.values(appIcons)) {
      const name = `mat${icon.replace(/(^|_)([a-z])/g, (_, _separator: string, letter: string) => letter.toUpperCase())}`
      expect(bundled.has(name), icon).toBe(true)
    }
  })
})
