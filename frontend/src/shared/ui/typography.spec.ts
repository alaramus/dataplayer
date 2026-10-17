import { describe, expect, it } from "vitest"

/**
 * A size of text is a role, as a space and a colour are (D185).
 *
 * The audit of 2026-09-28 found twelve sizes written as pixels — 9, 10, 11,
 * 12, 13, 14, 15, 17, 18, 20 and 24, and a 0.75rem — for what the scale in
 * metrics.css says in seven, and weights of 400, 500, 600 and 700 for three
 * roles. Every component style lives in a `.vue` file, which is what this
 * reads; metrics.css itself cannot be read from a unit test (layers.spec.ts
 * says why). A size relative to the text around it — `1em`, `inherit` — is a
 * size of no role of its own and stays allowed.
 */
const SOURCES = import.meta.glob("/src/**/*.vue", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

const STYLE = /<style[^>]*>([\s\S]*?)<\/style>/g
const COMMENT = /\/\*[\s\S]*?\*\//g
const SIZE = /(?:^|[;{\s])font-size\s*:\s*([^;}]+)/g
const WEIGHT = /(?:^|[;{\s])font-weight\s*:\s*([^;}]+)/g
const LINE = /(?:^|[;{\s])line-height\s*:\s*([^;}]+)/g
/* A `fontSize` or a `font-size` handed to an element or a library from a script. */
const SCRIPTED = /(?:fontSize\s*:|font-size\s*:)\s*["'`]?(\d+(?:\.\d+)?(?:px|rem))/g

const styles = Object.entries(SOURCES).flatMap(([path, text]) =>
  [...text.matchAll(STYLE)].map((style) => ({ path, css: (style[1] ?? "").replace(COMMENT, "") }))
)

const sizes = styles.flatMap(({ path, css }) =>
  [...css.matchAll(SIZE)].map((match) => ({ path, value: (match[1] ?? "").trim() }))
)
const weights = styles.flatMap(({ path, css }) =>
  [...css.matchAll(WEIGHT)].map((match) => ({ path, value: (match[1] ?? "").trim() }))
)

/* An icon is a glyph of a font, so its size is a font-size too — one of the
   three icon sizes. */
const ALLOWED_SIZE = /^(?:var\(--dp-(?:font-size(?:-[a-z]+)?|prose-[a-z0-9-]+|icon-[a-z]+)\)|inherit|1em)$/
const lines = styles.flatMap(({ path, css }) =>
  [...css.matchAll(LINE)].map((match) => ({ path, value: (match[1] ?? "").trim() }))
)
/* A line height is a role too: the audit of 2026-10-17 found 1.3, 1.4, 1.5,
   1.6, 1.65 and 20px beside the tokens. `1` sits a glyph on its own box, and
   `normal` hands a third-party layout (KaTeX) its own. */
const ALLOWED_LINE = /^(?:var\(--dp-(?:line-height(?:-[a-z]+)?|prose-[a-z-]*line-height)\)|1|normal|inherit)$/
const ALLOWED_WEIGHT = /^(?:400|500|600|normal|inherit)$/

describe("the sizes and weights of text", () => {
  it("are declared in many places, so this test has something to read", () => {
    // A glob or a pattern that matched nothing would make the assertions
    // below vacuous.
    expect(Object.keys(SOURCES).length).toBeGreaterThan(10)
    expect(sizes.length).toBeGreaterThan(100)
    expect(weights.length).toBeGreaterThan(30)
  })

  it("are spent from the type scale and never as pixels", () => {
    const off = sizes.filter((use) => !ALLOWED_SIZE.test(use.value))
    expect(off.map((use) => `${use.path}: font-size: ${use.value}`)).toEqual([])
  })

  it("set their lines from the scale", () => {
    expect(lines.length).toBeGreaterThan(20)
    const off = lines.filter((use) => !ALLOWED_LINE.test(use.value))
    expect(off.map((use) => `${use.path}: line-height: ${use.value}`)).toEqual([])
  })

  it("keep to the three weights", () => {
    const off = weights.filter((use) => !ALLOWED_WEIGHT.test(use.value))
    expect(off.map((use) => `${use.path}: font-weight: ${use.value}`)).toEqual([])
  })

  it("are not written as pixels from a script either", () => {
    const off = Object.entries(SOURCES).flatMap(([path, text]) =>
      [...text.replace(STYLE, "").matchAll(SCRIPTED)].map((match) => `${path}: ${match[0]}`)
    )
    expect(off).toEqual([])
  })
})
