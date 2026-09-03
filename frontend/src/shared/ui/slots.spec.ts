import { describe, expect, it } from "vitest"

/**
 * A kit component that takes its words in a slot must be given a slot.
 *
 * Vue lets an unknown attribute fall through to the rendered element, and
 * `vue-tsc` does not object, so `<AppBanner text="..." />` compiles, renders
 * and shows an empty coloured bar with an icon in it. That happened: the
 * window that shows a service's password warned about nothing at all, and it
 * took a screenshot to notice.
 *
 * The kit is deliberately not uniform here — `AppEmptyState` takes `text`
 * because it has one line and no rich content, `AppBanner` takes a slot
 * because banners carry sentences and links — and this is what stops the
 * difference being a trap.
 *
 * Reads `.vue` files, which is where every use of the kit is.
 */
const SOURCES = import.meta.glob("/src/**/*.vue", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

/** Kit components whose words go in a slot, never in an attribute. */
const SLOT_ONLY = ["AppBanner"]

const opening = (component: string) =>
  new RegExp(`<${component}\\b[^>]*`, "g")

const wrongly = SLOT_ONLY.flatMap((component) =>
  Object.entries(SOURCES).flatMap(([path, text]) =>
    [...text.matchAll(opening(component))]
      .filter((match) => /\s:?text=/.test(match[0]))
      .map(() => `${path}: <${component}> was given a text attribute`)
  )
)

describe("the kit components that take their words in a slot", () => {
  it("are used often enough for this test to have something to read", () => {
    const used = Object.values(SOURCES).filter((text) =>
      text.includes("<AppBanner")
    )
    expect(used.length).toBeGreaterThan(5)
  })

  it("are never given the words as an attribute instead", () => {
    expect(wrongly).toEqual([])
  })
})
