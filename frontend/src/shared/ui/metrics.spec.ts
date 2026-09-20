import { describe, expect, it } from "vitest"

/**
 * A space is a meaning, as a colour and a layer are: the audit of 2026-09-19
 * found 393 spacing and corner values written as pixels, 4, 6, 8, 10 and 12
 * side by side for what was meant to be one step.
 *
 * Every component style lives in a `.vue` file, and that is what this reads;
 * metrics.css itself cannot be read from a unit test (layers.spec.ts says why).
 * A hairline — `1px` — is a border's width rather than a space, and stays one.
 */
const SOURCES = import.meta.glob("/src/**/*.vue", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

const STYLE = /<style[^>]*>([\s\S]*?)<\/style>/g
const COMMENT = /\/\*[\s\S]*?\*\//g
const DECLARATION =
  /(?:^|[;{\s])((?:gap|row-gap|column-gap|padding(?:-[a-z-]+)?|margin(?:-[a-z-]+)?|border(?:-[a-z]+)*-radius)\s*:\s*[^;}]+)/g
const PIXELS = /(?<![\w.-])-?(\d+(?:\.\d+)?)px\b/g

const uses = Object.entries(SOURCES).flatMap(([path, text]) =>
  [...text.matchAll(STYLE)].flatMap((style) =>
    [...(style[1] ?? "").replace(COMMENT, "").matchAll(DECLARATION)].map((match) => ({
      path,
      declaration: (match[1] ?? "").trim(),
    }))
  )
)

describe("the spacing and the corners", () => {
  it("are declared in many places, so this test has something to read", () => {
    // A glob or a pattern that matched nothing would make the assertion
    // below vacuous.
    expect(Object.keys(SOURCES).length).toBeGreaterThan(10)
    expect(uses.length).toBeGreaterThan(100)
  })

  it("are spent from metrics.css and never as pixels", () => {
    const pixels = uses.filter((use) =>
      [...use.declaration.matchAll(PIXELS)].some((found) => found[1] !== "1")
    )
    expect(pixels.map((use) => `${use.path}: ${use.declaration}`)).toEqual([])
  })
})
