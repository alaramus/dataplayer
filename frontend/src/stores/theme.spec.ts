import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { THEME_KEY, useThemeStore } from "./theme"

/** What the browser would answer if nobody had chosen. */
function systemSays(dark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: dark && query.includes("dark"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  )
}

describe("theme store", () => {
  beforeEach(() => {
    localStorage.clear()
    document.body.className = ""
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("asks the system when nothing has been chosen yet", () => {
    systemSays(true)

    expect(useThemeStore().dark).toBe(true)
  })

  it("takes light from the system just as readily", () => {
    systemSays(false)

    expect(useThemeStore().dark).toBe(false)
  })

  it("prefers what was chosen here over what the system says", () => {
    systemSays(true)
    localStorage.setItem(THEME_KEY, "light")

    expect(useThemeStore().dark).toBe(false)
  })

  it("keeps the choice, so a reload finds it again", () => {
    systemSays(false)
    const theme = useThemeStore()

    theme.toggle()

    expect(theme.dark).toBe(true)
    expect(localStorage.getItem(THEME_KEY)).toBe("dark")
  })

  it("puts the choice on the body, which is what every colour keys off", () => {
    systemSays(false)
    const theme = useThemeStore()

    theme.apply()
    expect(document.body.classList.contains("body--dark")).toBe(false)

    theme.toggle()
    expect(document.body.classList.contains("body--dark")).toBe(true)

    theme.toggle()
    expect(document.body.classList.contains("body--dark")).toBe(false)
  })

  it("survives a browser with no matchMedia at all", () => {
    vi.stubGlobal("matchMedia", undefined)

    expect(useThemeStore().dark).toBe(false)
  })
})
