import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import page from "../../index.html?raw"

import { THEME_KEY, THEMES, useThemeStore } from "./theme"

/**
 * What the browser would answer, and a way to change its mind the way the
 * operating system does at sunset.
 */
function systemSays(dark: boolean) {
  const listeners: ((event: { matches: boolean }) => void)[] = []
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: dark && query.includes("dark"),
      media: query,
      addEventListener: (_: string, listener: (event: { matches: boolean }) => void) => {
        listeners.push(listener)
      },
      removeEventListener: vi.fn(),
    }))
  )
  return {
    turns: (next: boolean) => {
      for (const listener of listeners) listener({ matches: next })
    },
  }
}

describe("theme store", () => {
  beforeEach(() => {
    localStorage.clear()
    document.body.className = ""
    document.body.removeAttribute("data-dp-theme")
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("follows the system when nothing has been chosen yet", () => {
    systemSays(true)

    const theme = useThemeStore()

    expect(theme.mode).toBe("system")
    expect(theme.dark).toBe(true)
  })

  it("takes light from the system just as readily", () => {
    systemSays(false)

    expect(useThemeStore().dark).toBe(false)
  })

  it("prefers what was chosen here over what the system says", () => {
    systemSays(true)
    localStorage.setItem(THEME_KEY, "light")

    const theme = useThemeStore()

    expect(theme.mode).toBe("light")
    expect(theme.dark).toBe(false)
  })

  it("keeps the choice, so a reload finds it again", () => {
    systemSays(false)
    const theme = useThemeStore()

    theme.set("dark")

    expect(theme.dark).toBe(true)
    expect(localStorage.getItem(THEME_KEY)).toBe("dark")
  })

  it("goes back to the system by forgetting the choice", () => {
    systemSays(true)
    localStorage.setItem(THEME_KEY, "light")
    const theme = useThemeStore()

    theme.set("system")

    expect(theme.dark).toBe(true)
    expect(localStorage.getItem(THEME_KEY)).toBeNull()
  })

  it("turns over with the system while the system is followed", () => {
    const system = systemSays(false)
    const theme = useThemeStore()
    theme.apply()

    system.turns(true)

    expect(theme.dark).toBe(true)
    expect(document.body.classList.contains("body--dark")).toBe(true)
  })

  it("stays where it was put when the system turns over", () => {
    const system = systemSays(false)
    const theme = useThemeStore()
    theme.set("light")

    system.turns(true)
    expect(theme.dark).toBe(false)

    // And the answer is current when the system is followed again.
    theme.set("system")
    expect(theme.dark).toBe(true)
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

  it.each(["dark-blue", "paper", "midnight", "dark-purple"] as const)(
    "reads %s as a dark theme with its own ground",
    (mode) => {
      systemSays(false)
      localStorage.setItem(THEME_KEY, mode)

      const theme = useThemeStore()

      expect(theme.mode).toBe(mode)
      expect(theme.dark).toBe(true)
      expect(theme.variant).toBe(mode)
    }
  )

  it("marks a named ground beside the dark class, and clears the mark after it", () => {
    systemSays(false)
    const theme = useThemeStore()

    theme.set("dark-blue")
    expect(document.body.classList.contains("body--dark")).toBe(true)
    expect(document.body.dataset.dpTheme).toBe("dark-blue")

    theme.set("dark")
    expect(document.body.classList.contains("body--dark")).toBe(true)
    expect(document.body.dataset.dpTheme).toBeUndefined()

    // Dark to a named ground turns over without `dark` changing at all.
    theme.set("paper")
    expect(document.body.classList.contains("body--dark")).toBe(true)
    expect(document.body.dataset.dpTheme).toBe("paper")

    theme.set("paper")
    theme.set("system")
    expect(document.body.dataset.dpTheme).toBeUndefined()
  })

  it("reads paper-light as a light theme carrying its own ground", () => {
    systemSays(true)
    localStorage.setItem(THEME_KEY, "paper-light")

    const theme = useThemeStore()

    expect(theme.mode).toBe("paper-light")
    expect(theme.dark).toBe(false)
    expect(theme.variant).toBe("paper-light")

    theme.apply()
    expect(document.body.classList.contains("body--dark")).toBe(false)
    expect(document.body.dataset.dpTheme).toBe("paper-light")
  })

  it("leaves a named ground for light when no light theme was chosen", () => {
    systemSays(false)
    const theme = useThemeStore()
    theme.set("paper")

    theme.toggle()

    expect(theme.mode).toBe("light")
    expect(document.body.dataset.dpTheme).toBeUndefined()
  })

  it("toggles between the last light and the last dark theme chosen", () => {
    systemSays(false)
    const theme = useThemeStore()
    theme.set("paper-light")
    theme.set("midnight")
    expect(theme.opposite.label).toBe("Paper light")

    theme.toggle()
    expect(theme.mode).toBe("paper-light")
    expect(theme.opposite.label).toBe("Midnight")

    theme.toggle()
    expect(theme.mode).toBe("midnight")
    expect(document.body.dataset.dpTheme).toBe("midnight")
  })

  it("forgets a remembered theme of the wrong polarity", () => {
    systemSays(false)
    localStorage.setItem("dataplayer-theme-dark", "paper-light")
    const theme = useThemeStore()
    theme.set("light")

    theme.toggle()

    expect(theme.mode).toBe("dark")
  })

  it.each(THEMES.map((theme) => [theme.value, theme.dark] as const))(
    "is put on the page before the first paint: %s, dark %s",
    (value, dark) => {
      // index.html repeats the polarities, because it runs before the bundle.
      const list = page.match(new RegExp(`var ${dark ? "dark" : "light"} = \\[([^\\]]*)\\]`))?.[1] ?? ""
      expect(list).toContain(`"${value}"`)
    }
  )

  it("names no theme before the first paint that the store does not know", () => {
    const named = [...page.matchAll(/var (?:dark|light) = \[([^\]]*)\]/g)].flatMap((match) =>
      [...(match[1] ?? "").matchAll(/"([a-z-]+)"/g)].map((id) => id[1])
    )
    expect(named.sort()).toEqual(THEMES.map((theme) => theme.value).sort())
  })
})
