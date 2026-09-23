import { describe, expect, it } from "vitest"

import bundledIcons from "@quasar/extras/material-icons/icons.json"
import outlinedSymbols from "@quasar/extras/material-symbols-outlined/icons.json"

import { appIcons, iconComparison, symbolComparisonIcon } from "./icons"

describe("shared semantic icons", () => {
  const keyOf = (prefix: string, icon: string) =>
    `${prefix}${icon.replace(/(^|_)([a-z])/g, (_, _separator: string, letter: string) => letter.toUpperCase())}`

  it("uses glyphs available in the installed Material Icons font", () => {
    const bundled = new Set(bundledIcons)
    for (const icon of Object.values(appIcons)) {
      expect(bundled.has(keyOf("mat", icon)), icon).toBe(true)
    }
  })

  it("can show the same names in the UI kit comparison font", () => {
    const bundled = new Set(outlinedSymbols)
    for (const { icon } of iconComparison) {
      expect(bundled.has(keyOf("symOutlined", symbolComparisonIcon(icon))), icon).toBe(true)
    }
  })

  it("keeps literal icon names out of button templates", () => {
    const sources = import.meta.glob("/src/**/*.vue", { query: "?raw", import: "default", eager: true })
    const offenders = Object.entries(sources).filter(([, source]) =>
      /<(?:AppButton|AppIconButton|AppTaskbarItem|q-btn)\b[^>]*(?<![:\w-])icon(?:-right)?="[a-z_]+"/s.test(source as string)
    )
    expect(offenders.map(([path]) => path)).toEqual([])
  })
})
