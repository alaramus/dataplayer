import { describe, expect, it } from "vitest"

/**
 * A layer is a meaning, as a colour is: the window engine once lost to a
 * sticky table heading that declared `1`, and the drop zone lost to the same
 * heading afterwards.
 *
 * This reads `.vue` files, where every component style lives. A `.css` file
 * cannot be read from a unit test at all — `import.meta.glob` and `?raw` both
 * hand back the name and an empty string — so the scale's own order is checked
 * in the browser, by the Playwright scenario about a sticky heading.
 */
const SOURCES = import.meta.glob("/src/**/*.vue", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

const DECLARED = /z-index:\s*([^;]+);/g

const uses = Object.entries(SOURCES).flatMap(([path, text]) =>
  [...text.matchAll(DECLARED)].map((match) => ({ path, value: (match[1] ?? "").trim() }))
)

describe("the stacking order", () => {
  it("is declared in more than one place, so this test has something to read", () => {
    // A glob that matched nothing would make the assertion below vacuous.
    expect(Object.keys(SOURCES).length).toBeGreaterThan(10)
    expect(uses.length).toBeGreaterThan(2)
  })

  it("is spent by name and never as a number", () => {
    const numbers = uses.filter((use) => !/^var\(--dp-layer-[a-z-]+\)$/.test(use.value))
    expect(numbers.map((use) => `${use.path}: ${use.value}`)).toEqual([])
  })
})
