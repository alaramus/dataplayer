import { describe, expect, it } from "vitest"

/**
 * A layer is a meaning, exactly as a colour is.
 *
 * Whatever floats above the page has to say how far above it floats, and a
 * screen that answers with a number answers alone: the window engine once lost
 * to a sticky table heading that declared `1`, and the drop zone of the
 * workspace lost to the same heading afterwards. `layers.css` is the one place
 * the order is decided, so two of them can be compared by reading one file.
 */
const SOURCES = import.meta.glob("/src/**/*.{vue,css}", {
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
    // A glob that matched nothing would make every assertion below vacuous.
    expect(uses.length).toBeGreaterThan(2)
  })

  it("is spent by name and never as a number", () => {
    const numbers = uses.filter((use) => !/^var\(--dp-layer-[a-z-]+\)$/.test(use.value))
    expect(numbers.map((use) => `${use.path}: ${use.value}`)).toEqual([])
  })
})
