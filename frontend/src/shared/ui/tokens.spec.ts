import { describe, expect, it } from "vitest"

import { bannerLook, buttonLook, panelStyle } from "./tokens"

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
    expect(buttonLook("primary")).toEqual({ color: "primary", flat: false })
    expect(buttonLook("danger")).toEqual({ color: "negative", flat: false })
    expect(buttonLook("secondary").flat).toBe(true)
    expect(buttonLook("danger-quiet").flat).toBe(true)
    expect(buttonLook("quiet").flat).toBe(true)
  })

  it("carries the destructive colour in both destructive variants", () => {
    expect(buttonLook("danger").color).toBe("negative")
    expect(buttonLook("danger-quiet").color).toBe("negative")
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

  // A Playwright scenario asserts this class on the connection check result.
  it("keeps the classes the existing screens were built on", () => {
    expect(bannerLook("error").classes).toContain("bg-negative")
    expect(bannerLook("success").classes).toContain("bg-positive")
  })
})
