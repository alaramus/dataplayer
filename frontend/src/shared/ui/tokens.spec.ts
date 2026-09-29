import { describe, expect, it } from "vitest"

import { bannerLook, buttonLook, checkboxLook, panelStyle } from "./tokens"

describe("panelStyle", () => {
  it("gives every size a width and a viewport ceiling", () => {
    for (const size of ["xs", "sm", "md", "lg"] as const) {
      const style = panelStyle(size)

      expect(style.width).toMatch(/^\d+px$/)
      expect(style.maxWidth).toMatch(/^\d+vw$/)
    }
  })

  it("orders the sizes by width", () => {
    const width = (size: "xs" | "sm" | "md" | "lg") =>
      Number.parseInt(panelStyle(size).width, 10)

    expect(width("xs")).toBeLessThan(width("sm"))
    expect(width("sm")).toBeLessThan(width("md"))
    expect(width("md")).toBeLessThan(width("lg"))
  })
})

describe("buttonLook", () => {
  it("makes the main action solid and the rest flat", () => {
    expect(buttonLook("primary")).toEqual({
      color: "dp-action-primary", textColor: "dp-on-action-primary", unelevated: true, flat: false,
    })
    expect(buttonLook("danger")).toEqual({ color: "negative", unelevated: true, flat: false })
    expect(buttonLook("secondary").flat).toBe(true)
    expect(buttonLook("danger-quiet").flat).toBe(true)
    expect(buttonLook("quiet").flat).toBe(true)
  })

  it("separates filled colours from theme-aware action text", () => {
    expect(buttonLook("danger").color).toBe("negative")
    expect(buttonLook("danger-quiet").color).toBe("dp-action-danger")
    expect(buttonLook("secondary").color).toBe("dp-action-secondary")
  })

  it("fills the chosen one of a row, so it is the one that stands out", () => {
    // Written as secondary it was a grey dimmer than the quiet buttons beside
    // it in the dark theme: the space you were in stood out least.
    expect(buttonLook("chosen").flat).toBe(false)
    expect(buttonLook("chosen").color).toBe("dp-action-primary")
    expect(buttonLook("chosen").textColor).toBe("dp-on-action-primary")
  })

  // The view being shown is drawn the way a current tab is, not like the main
  // action beside it: "Tree" read the same as "Run" (D187).
  it("draws the current view on the ground of a current tab", () => {
    expect(buttonLook("current").color).toBe("dp-tab-current")
    expect(buttonLook("current").textColor).toBe("dp-action-secondary")
    expect(buttonLook("current").color).not.toBe(buttonLook("primary").color)
  })

  // Cancel and Close must not compete with the action next to them.
  it("leaves the quiet variant without a colour", () => {
    expect(buttonLook("quiet").color).toBeUndefined()
  })
})

describe("bannerLook", () => {
  it("gives every tone a class and an icon", () => {
    for (const tone of ["error", "success", "warning", "info"] as const) {
      const look = bannerLook(tone)

      expect(look.classes).not.toBe("")
      expect(look.icon).not.toBe("")
    }
  })

  // Quasar's own colour classes are one colour for both themes, which is how a
  // dark red banner came to sit on a dark surface (U08).
  it("names a theme class rather than one of Quasar's colours", () => {
    for (const tone of ["error", "success", "warning", "info"] as const) {
      expect(bannerLook(tone).classes).toMatch(/^dp-tone-/)
    }
  })
})

describe("checkboxLook", () => {
  // One look in or out of a form (D186): a box outside one used to come out
  // in Quasar's brand blue next to a form's neutral one.
  it("marks a tick box with the neutral colour everywhere", () => {
    for (const form of [false, true]) {
      expect(checkboxLook(form, false).color).toBe("dp-control-selected")
      expect(checkboxLook(form, true).color).toBe("dp-control-selected")
    }
  })

  it("stays dense in a form or when asked", () => {
    expect(checkboxLook(false, false).dense).toBe(false)
    expect(checkboxLook(false, true).dense).toBe(true)
    expect(checkboxLook(true, false).dense).toBe(true)
  })
})
