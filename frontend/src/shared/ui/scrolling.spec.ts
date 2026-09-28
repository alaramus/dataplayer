import { describe, expect, it } from "vitest"

/**
 * Every box that scrolls says where its scroll chain ends.
 *
 * Trap: Chrome decides which box a gesture scrolls by its first movement. A
 * list already at its top, pushed up first, can take nothing, so the gesture
 * went on up the chain to the page — which does not scroll — and stayed there:
 * pulling back down in the same gesture moved nothing until the fingers
 * lifted. Firefox asks at every event and never showed it. A box whose
 * `overscroll-behavior` is not `auto` ends the chain, and Chrome then keeps the
 * gesture for that box, so the way back scrolls it.
 *
 * So a list declares `contain`. `auto` is a decision too, and a rare one: a
 * wide table in a text scrolls sideways and has to hand a turned wheel on to
 * the text around it. Quasar's own scrolling boxes — a menu, a scroll area —
 * are given `contain` once, in scrolling.css.
 */
const SOURCES = import.meta.glob("/src/**/*.vue", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

const STYLE = /<style[^>]*>([\s\S]*?)<\/style>/g
const COMMENT = /\/\*[\s\S]*?\*\//g
/** An innermost rule: a selector and a body holding no rule of its own. */
const RULE = /([^{}]+)\{([^{}]*)\}/g
const SCROLLS = /(?:^|[;\s])overflow(?:-y)?\s*:\s*(?:auto|scroll|overlay)\b/

const scrollers = Object.entries(SOURCES).flatMap(([path, text]) =>
  [...text.matchAll(STYLE)].flatMap((style) =>
    [...(style[1] ?? "").replace(COMMENT, "").matchAll(RULE)]
      .filter((rule) => SCROLLS.test(` ${rule[2] ?? ""}`))
      .map((rule) => ({ path, selector: (rule[1] ?? "").trim().replace(/\s+/g, " "), body: rule[2] ?? "" }))
  )
)

describe("the boxes that scroll", () => {
  it("are many, so this test has something to read", () => {
    expect(scrollers.length).toBeGreaterThan(40)
  })

  it("each say where their scroll chain ends", () => {
    const silent = scrollers.filter((scroller) => !/overscroll-behavior(?:-y)?\s*:/.test(scroller.body))
    expect(silent.map((scroller) => `${scroller.path}: ${scroller.selector}`)).toEqual([])
  })
})
