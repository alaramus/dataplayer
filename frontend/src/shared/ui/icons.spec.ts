import { describe, expect, it } from "vitest"

import outlinedSymbols from "@quasar/extras/material-symbols-outlined/icons.json"

import { appIcons, namedIcons } from "./icons"

describe("shared semantic icons", () => {
  const keyOf = (prefix: string, icon: string) =>
    `${prefix}${icon.replace(/(^|_)([a-z])/g, (_, _separator: string, letter: string) => letter.toUpperCase())}`

  it("uses glyphs available in the installed Symbols Outlined font", () => {
    const bundled = new Set(outlinedSymbols)
    for (const icon of Object.values(appIcons)) {
      expect(bundled.has(keyOf("symOutlined", icon)), icon).toBe(true)
    }
  })

  it("lists every semantic icon in the UI kit", () => {
    expect(namedIcons).toEqual(Object.entries(appIcons).map(([name, icon]) => ({ name, icon })))
  })

  it("keeps literal icon names out of button templates", () => {
    const sources = import.meta.glob("/src/**/*.vue", { query: "?raw", import: "default", eager: true })
    const offenders = Object.entries(sources).filter(([, source]) =>
      /<(?:AppButton|AppIconButton|AppTaskbarItem|q-btn)\b[^>]*(?<![:\w-])icon(?:-right)?="[a-z_]+"/s.test(source as string)
    )
    expect(offenders.map(([path]) => path)).toEqual([])
  })
})
