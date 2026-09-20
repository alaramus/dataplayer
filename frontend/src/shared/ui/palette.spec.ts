import { describe, expect, it } from "vitest"

/**
 * Every colour is theme.css's, so it turns over with the theme.
 *
 * Three ways around that were found in the audit of 2026-09-19, and each is a
 * test here: a colour written as a number (`#d32f2f` behind a token nobody had
 * declared), Quasar's palette reached for as `var(--q-negative)` — one colour
 * for both themes, dark red on a dark menu — and Quasar's colour classes
 * (`text-negative`, `bg-positive`) built by a screen rather than by the kit.
 *
 * The kit (`src/shared/ui`) may speak Quasar's names: `tokens.ts` is the one
 * place meaning becomes a Quasar prop. `panelColor.ts` computes the colours a
 * person chose for a connection, which are data rather than a palette.
 */
const COMPONENTS = import.meta.glob("/src/**/*.vue", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>
const MODULES = import.meta.glob(["/src/**/*.ts", "!/src/**/*.spec.ts", "!/src/client/**"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

const STYLE = /<style[^>]*>([\s\S]*?)<\/style>/g
const BLOCK_COMMENT = /\/\*[\s\S]*?\*\//g
const LINE_COMMENT = /(^|[^:])\/\/.*$/gm
const HTML_COMMENT = /<!--[\s\S]*?-->/g
const LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/g
const QUASAR_VARIABLE = /var\(--q-[a-z-]+\)/g
const QUASAR_CLASS =
  /\b(?:text|bg)-(?:primary|secondary|accent|dark|positive|negative|info|warning|white|black|grey(?:-\d+)?|red(?:-\d+)?|green(?:-\d+)?|blue(?:-\d+)?|orange(?:-\d+)?|amber(?:-\d+)?)\b/g

const KIT = "/src/shared/ui/"
const CHOSEN_COLOURS = "/src/shared/ui/panelColor.ts"

function found(files: Record<string, string>, pattern: RegExp, read: (text: string) => string) {
  return Object.entries(files).flatMap(([path, text]) =>
    [...read(text).matchAll(pattern)].map((match) => `${path}: ${match[0]}`)
  )
}

const styles = (text: string) =>
  [...text.matchAll(STYLE)].map((style) => (style[1] ?? "").replace(BLOCK_COMMENT, "")).join("\n")
const code = (text: string) =>
  text.replace(HTML_COMMENT, "").replace(BLOCK_COMMENT, "").replace(LINE_COMMENT, "$1")
const outsideKit = (files: Record<string, string>) =>
  Object.fromEntries(Object.entries(files).filter(([path]) => !path.startsWith(KIT)))

describe("the palette", () => {
  it("has components and modules to read", () => {
    expect(Object.keys(COMPONENTS).length).toBeGreaterThan(10)
    expect(Object.keys(MODULES).length).toBeGreaterThan(10)
  })

  it("is never written as a number in a component's style", () => {
    expect(found(COMPONENTS, LITERAL, styles)).toEqual([])
  })

  it("is never written as a number in a module", () => {
    const modules = Object.fromEntries(
      Object.entries(MODULES).filter(([path]) => path !== CHOSEN_COLOURS)
    )
    expect(found(modules, LITERAL, code)).toEqual([])
  })

  it("never reaches past the theme for Quasar's own colours", () => {
    expect([
      ...found(COMPONENTS, QUASAR_VARIABLE, code),
      ...found(MODULES, QUASAR_VARIABLE, code),
    ]).toEqual([])
  })

  it("is chosen by meaning outside the kit, never by a Quasar colour class", () => {
    expect([
      ...found(outsideKit(COMPONENTS), QUASAR_CLASS, code),
      ...found(outsideKit(MODULES), QUASAR_CLASS, code),
    ]).toEqual([])
  })
})
