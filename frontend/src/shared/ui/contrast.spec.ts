import { readFileSync } from "node:fs"

import { describe, expect, it } from "vitest"

/**
 * Every theme is legible, measured rather than picked by eye (D196).
 *
 * The audit of 2026-10-02 found a link at 3.9:1, tab captions at 4.2:1, an
 * error under a field at 2.9:1 and three themes whose frame and head stood in
 * the reverse of the order every card is drawn for — each in a theme somebody
 * had checked by looking at it. This reads `theme.css` from the disk, resolves
 * each theme the way the browser does, lays every translucent colour over the
 * ground it sits on and holds the result to WCAG 2.2's floors: 4.5:1 for
 * text, 3:1 for a mark a control is found by.
 *
 * Read from the disk because Vite hands a test an empty string for a `.css`
 * file; a path is relative to `frontend/`, where vitest runs.
 */

interface Colour {
  r: number
  g: number
  b: number
  a: number
}

type Declarations = Map<string, string>

const CSS = readFileSync("src/shared/ui/theme.css", "utf-8").replace(/\/\*[\s\S]*?\*\//g, "")

/** Every innermost rule that declares a custom property, by its selector. */
const RULES = [...CSS.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
  selector: (match[1] ?? "").trim().replace(/\s+/g, " "),
  declarations: new Map(
    [...(match[2] ?? "").matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)].map(
      (found) => [found[1] ?? "", (found[2] ?? "").trim()] as const
    )
  ) as Declarations,
}))

function rule(selector: string): Declarations {
  const found = RULES.filter((entry) => entry.selector === selector)
  return new Map(found.flatMap((entry) => [...entry.declarations]))
}

const ROOT = rule(":root")

const NAMED = /^body(\.body--dark|:not\(\.body--dark\))\[data-dp-theme="([a-z-]+)"\]$/

interface Theme {
  name: string
  dark: boolean
  named: boolean
  /** What the body declares, in cascade order: later wins. */
  body: Declarations
  /** What the theme's own rule declares, for a named one. */
  own: Declarations
}

const THEMES: Theme[] = [
  { name: "light", dark: false, named: false, body: rule("body"), own: new Map() },
  {
    name: "dark",
    dark: true,
    named: false,
    body: new Map([...rule("body"), ...rule("body.body--dark")]),
    own: new Map(),
  },
  ...RULES.flatMap((entry) => {
    const match = entry.selector.match(NAMED)
    if (match === null) return []
    const dark = match[1] === ".body--dark"
    // `body` < `body.body--dark` < the marker, by specificity.
    const body = new Map([
      ...rule("body"),
      ...(dark ? rule("body.body--dark") : []),
      ...entry.declarations,
    ])
    return [{ name: match[2] ?? "", dark, named: true, body, own: entry.declarations }]
  }),
]

function parse(text: string): Colour {
  if (text === "transparent") return { r: 0, g: 0, b: 0, a: 0 }
  const hex = text.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)?.[1]
  if (hex !== undefined) {
    const full = hex.length === 3 ? [...hex].map((digit) => digit + digit).join("") : hex
    const channel = (at: number) => Number.parseInt(full.slice(at, at + 2), 16)
    return { r: channel(0), g: channel(2), b: channel(4), a: 1 }
  }
  const rgb = text.match(/^rgba?\(([^)]*)\)$/)?.[1]
  if (rgb !== undefined) {
    const parts = rgb.split(/[\s,/]+/).filter(Boolean)
    const [r, g, b] = parts.slice(0, 3).map(Number)
    const alpha = parts[3]
    const a = alpha === undefined ? 1 : alpha.endsWith("%") ? Number(alpha.slice(0, -1)) / 100 : Number(alpha)
    return { r: r ?? 0, g: g ?? 0, b: b ?? 0, a }
  }
  throw new Error(`not a colour: ${text}`)
}

/** Arguments at the top level of a function, nested brackets kept whole. */
function args(text: string): string[] {
  const found: string[] = []
  let depth = 0
  let current = ""
  for (const character of text) {
    if (character === "(") depth += 1
    if (character === ")") depth -= 1
    if (character === "," && depth === 0) {
      found.push(current.trim())
      current = ""
    } else current += character
  }
  return [...found, current.trim()]
}

/**
 * What a custom property computes to on the body.
 *
 * A custom property is substituted on the element that declares it: what
 * the body does not declare it inherits from :root as :root computed it, with
 * :root's values, which is why theme.css writes some tokens twice.
 */
function resolver(theme: Theme) {
  function value(name: string, scope: "root" | "body"): Colour {
    if (scope === "body" && theme.body.has(name)) return evaluate(theme.body.get(name) ?? "", "body")
    const declared = ROOT.get(name)
    if (declared === undefined) throw new Error(`${name} is declared nowhere`)
    return evaluate(declared, "root")
  }
  function evaluate(text: string, scope: "root" | "body"): Colour {
    const reference = text.match(/^var\((--[a-z0-9-]+)\)$/)?.[1]
    if (reference !== undefined) return value(reference, scope)
    const mix = text.match(/^color-mix\(in srgb,(.*)\)$/)?.[1]
    if (mix !== undefined) {
      const [first, second] = args(mix).map((part) => {
        const weight = part.match(/\s(\d+(?:\.\d+)?)%$/)
        return { colour: evaluate(weight ? part.slice(0, weight.index).trim() : part, scope), weight: weight ? Number(weight[1]) / 100 : null }
      })
      if (first === undefined || second === undefined) throw new Error(`a mix of one: ${text}`)
      const p = first.weight ?? 1 - (second.weight ?? 0.5)
      const q = second.weight ?? 1 - p
      // Premultiplied, as the browser mixes.
      const a = first.colour.a * p + second.colour.a * q
      const channel = (key: "r" | "g" | "b") =>
        a === 0 ? 0 : (first.colour[key] * first.colour.a * p + second.colour[key] * second.colour.a * q) / a
      return { r: channel("r"), g: channel("g"), b: channel("b"), a }
    }
    return parse(text)
  }
  return (name: string) => value(`--dp-${name}`, "body")
}

function over(top: Colour, ground: Colour): Colour {
  const blend = (key: "r" | "g" | "b") => top[key] * top.a + ground[key] * (1 - top.a)
  return { r: blend("r"), g: blend("g"), b: blend("b"), a: 1 }
}

function luminance(colour: Colour): number {
  const linear = (channel: number) => {
    const value = channel / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * linear(colour.r) + 0.7152 * linear(colour.g) + 0.0722 * linear(colour.b)
}

function contrast(one: Colour, other: Colour): number {
  const [light, dark] = [luminance(one), luminance(other)].sort((x, y) => y - x)
  return ((light ?? 0) + 0.05) / ((dark ?? 0) + 0.05)
}

/** The hue angle in CIELAB, where "the same family" is measured. */
function hue(colour: Colour): number {
  const linear = (channel: number) => {
    const value = channel / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }
  const [r, g, b] = [linear(colour.r), linear(colour.g), linear(colour.b)]
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116)
  const x = f((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047)
  const y = f(0.2126 * r + 0.7152 * g + 0.0722 * b)
  const z = f((0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883)
  return ((Math.atan2(200 * (y - z), 500 * (x - y)) * 180) / Math.PI + 360) % 360
}

const GROUNDS = [
  "surface",
  "surface-raised",
  "card-head",
  "chrome",
  "chrome-raised",
  "tab-current",
  "panel-plain",
  "panel-plain-quiet",
  "field-surface",
]

/** What a named theme may not leave to the theme beneath it (D196). */
const OWN = [
  "surface",
  "surface-raised",
  "chrome",
  "chrome-raised",
  "card-head",
  "field-surface",
  "field-border",
  "tab-current",
  "panel-plain",
  "panel-plain-quiet",
  "accent",
  "link",
  "selected",
  "selected-quiet",
  "text-selection",
  "info",
  "tone-info-wash",
  "dropzone",
  "dropzone-border",
]

describe("the themes", () => {
  it("are read from the file that declares them", () => {
    expect(ROOT.size).toBeGreaterThan(50)
    expect(THEMES.map((theme) => theme.name).sort()).toEqual(
      ["dark", "dark-blue", "dark-purple", "light", "midnight", "paper", "paper-light"]
    )
  })
})

describe.each(THEMES.map((theme) => [theme.name, theme] as const))("%s", (_, theme) => {
  const token = resolver(theme)
  const surface = token("surface")
  /** A token as it is painted: over the surface when it lets it through. */
  const solid = (name: string, ground: Colour = surface) => over(token(name), ground)
  const ratio = (ink: string, ground: string) => {
    const under = solid(ground)
    return contrast(over(token(ink), under), under)
  }
  const failing = (inks: string[], grounds: string[], floor: number) =>
    inks.flatMap((ink) =>
      grounds
        .map((ground) => ({ ink, ground, ratio: Number(ratio(ink, ground).toFixed(2)) }))
        .filter((pair) => pair.ratio < floor)
    )

  it("reads text and secondary text at 4.5:1 on every ground", () => {
    expect(failing(["text", "text-muted"], GROUNDS, 4.5)).toEqual([])
  })

  it("reads a link, the accent and a note at 4.5:1 wherever they are written", () => {
    expect(failing(["link", "accent", "info"], ["surface", "surface-raised", "card-head"], 4.5)).toEqual([])
  })

  it("reads every tone at 4.5:1", () => {
    expect(
      failing(
        ["content-error", "content-success", "tone-warning-text", "action-danger"],
        ["surface", "surface-raised"],
        4.5
      )
    ).toEqual([])
    const washes = ["tone-error-wash", "tone-success-wash", "tone-warning-wash", "tone-info-wash"]
    expect(failing(["on-wash"], washes, 4.5)).toEqual([])
    expect(failing(["on-fill"], ["danger-fill"], 4.5)).toEqual([])
    expect(failing(["on-action-primary"], ["action-primary"], 4.5)).toEqual([])
  })

  it("draws the marks a control is found by at 3:1", () => {
    expect(failing(["focus-border"], GROUNDS, 3)).toEqual([])
    expect(failing(["field-border"], ["field-surface"], 3)).toEqual([])
    expect(failing(["text-faint", "dropzone-border"], ["surface"], 3)).toEqual([])
  })

  it("tells a chosen row from a hovered one, and a banner from the page", () => {
    expect(contrast(solid("selected"), solid("hover"))).toBeGreaterThanOrEqual(1.1)
    for (const wash of ["tone-error-wash", "tone-success-wash", "tone-warning-wash", "tone-info-wash"]) {
      expect(contrast(solid(wash), surface), wash).toBeGreaterThanOrEqual(1.08)
    }
    expect(contrast(token("tone-info-wash"), token("surface-raised"))).toBeGreaterThanOrEqual(1.08)
  })

  it("stacks its grounds in the order every card is drawn for", () => {
    // How far a ground stands from the surface towards the middle: darker in
    // a light theme, lighter in a dark one.
    const step = (name: string) =>
      (theme.dark ? 1 : -1) * (luminance(solid(name)) - luminance(surface))
    expect(step("chrome-raised"), "the frame beyond the surface").toBeGreaterThan(0)
    expect(step("card-head"), "the head beyond the surface").toBeGreaterThan(0)
    expect(step("tab-current"), "the current tab beyond its head").toBeGreaterThan(step("card-head"))
    expect(step("panel-plain"), "a tab beyond its head").toBeGreaterThan(step("card-head"))
    expect(step("chrome"), "a window's bar beyond its frame").toBeGreaterThan(step("surface-raised"))
  })

  it("keeps a note apart from a warning and an error", () => {
    // 60° is another family: a bronze note 8° from an amber warning and a
    // pink one 32° from a salmon error each read as the other.
    const apart = (one: string, other: string) => {
      const distance = Math.abs(hue(token(one)) - hue(token(other)))
      return Math.min(distance, 360 - distance)
    }
    expect(apart("info", "tone-warning-text")).toBeGreaterThanOrEqual(60)
    expect(apart("info", "content-error")).toBeGreaterThanOrEqual(60)
  })

  it.runIf(theme.named)("declares its own grounds, accent and note", () => {
    expect(OWN.filter((name) => !theme.own.has(`--dp-${name}`))).toEqual([])
  })
})
