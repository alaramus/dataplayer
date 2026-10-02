import { defineStore } from "pinia"
import { Dark } from "quasar"
import { computed, ref, watch } from "vue"

export const THEME_KEY = "dataplayer-theme"
/** The last light and the last dark theme chosen, which the toggle returns to. */
export const LIGHT_THEME_KEY = "dataplayer-theme-light"
export const DARK_THEME_KEY = "dataplayer-theme-dark"

/**
 * Every theme there is, once. Preferences lists these in this order, and
 * `index.html` repeats the ids and polarities to put the choice on the page
 * before the first paint.
 *
 * `named` is a palette of its own (D196), selected by a `data-dp-theme`
 * marker beside Quasar's dark class: the dark ones carry `body--dark` too,
 * paper-light carries the marker without it.
 */
export const THEMES = [
  { value: "light", label: "Light", dark: false, named: false },
  {
    value: "paper-light",
    label: "Paper light",
    description: "Warm light paper with a bronze accent",
    dark: false,
    named: true,
  },
  { value: "dark", label: "Dark", dark: true, named: false },
  {
    value: "paper",
    // Labelled by its polarity: beside Paper light, plain Paper read as the
    // light one. The id stays, so a stored choice still finds it.
    label: "Paper dark",
    description: "Warm dark paper with a bronze accent",
    dark: true,
    named: true,
  },
  {
    value: "midnight",
    label: "Midnight",
    description: "The dimmest: near-black navy with an ice-blue accent",
    dark: true,
    named: true,
  },
  {
    value: "dark-blue",
    label: "Dark blue",
    description: "Saturated navy with a cyan accent",
    dark: true,
    named: true,
  },
  {
    value: "dark-purple",
    label: "Dark purple",
    description: "Purple neon with pink and cyan accents",
    dark: true,
    named: true,
  },
] as const

type Theme = (typeof THEMES)[number]
export type ThemeName = Theme["value"]

/**
 * A theme, or whatever the system says. Pinia, because the server knows
 * nothing about it (D6). System is the default and a choice of its own: a
 * person who picked Light can go back to following the machine, whose theme
 * may change at sunset while the page stays open.
 *
 * The one place that names Quasar's Dark plugin. It puts `body--dark` on the
 * document and `shared/ui/theme.css` hangs every colour of ours off the same
 * class, so the kit and the screens turn over on one event rather than two.
 */
export type ThemeMode = ThemeName | "system"

/** A theme with its own palette, or nothing for the two plain ones. */
export type ThemeVariant = Extract<Theme, { named: true }>["value"] | null

const QUERY = "(prefers-color-scheme: dark)"

function themeOf(value: string | null): Theme | undefined {
  return THEMES.find((theme) => theme.value === value)
}

/** What the browser was told to prefer. */
export function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(QUERY).matches
}

function chosen(): ThemeMode {
  return themeOf(localStorage.getItem(THEME_KEY))?.value ?? "system"
}

/** The last theme of one polarity chosen here, or the plain one. */
function last(dark: boolean): ThemeName {
  const found = themeOf(localStorage.getItem(dark ? DARK_THEME_KEY : LIGHT_THEME_KEY))
  return found?.dark === dark ? found.value : dark ? "dark" : "light"
}

export const useThemeStore = defineStore("theme", () => {
  const mode = ref<ThemeMode>(chosen())
  const systemDark = ref(systemPrefersDark())
  const dark = computed(() =>
    mode.value === "system" ? systemDark.value : (themeOf(mode.value)?.dark ?? false)
  )
  const variant = computed<ThemeVariant>(() => {
    const theme = themeOf(mode.value)
    return theme?.named ? theme.value : null
  })

  // Listened to for the life of the page, whatever is chosen: switching to
  // System later must find the answer current, not the one read at start.
  if (typeof window.matchMedia === "function") {
    window.matchMedia(QUERY).addEventListener("change", (event) => {
      systemDark.value = event.matches
    })
  }

  /**
   * Put the current choice on the document.
   *
   * Called from `main.ts` before the application is mounted. `index.html`
   * has put it there already, before the first paint, and Quasar's install
   * has just written light over it.
   */
  function apply() {
    Dark.set(dark.value)
    // A named ground is a marker beside the dark class, not instead of it:
    // removing the choice must leave no trace for the next theme to inherit.
    if (variant.value) document.body.dataset.dpTheme = variant.value
    else document.body.removeAttribute("data-dp-theme")
  }
  // Both halves of what apply() reads: dark to a named ground leaves `dark`
  // unchanged, so watching it alone would never put the marker on.
  watch([dark, variant], apply, { flush: "sync" })

  function set(value: ThemeMode) {
    mode.value = value
    // Nothing stored is System, so an old browser and a new choice agree.
    if (value === "system") {
      localStorage.removeItem(THEME_KEY)
      return
    }
    localStorage.setItem(THEME_KEY, value)
    localStorage.setItem(themeOf(value)?.dark ? DARK_THEME_KEY : LIGHT_THEME_KEY, value)
  }

  /** Where the toggle goes: the last theme of the other polarity. */
  const opposite = computed(() => {
    const value = last(!dark.value)
    return THEMES.find((theme) => theme.value === value) ?? THEMES[0]
  })

  /**
   * The other polarity, chosen outright, whatever answered before. It lands
   * on the last theme of that polarity chosen here — Paper dark goes to Paper
   * light and back — and on Light or Dark when none was.
   */
  function toggle() {
    set(opposite.value.value)
  }

  return { mode, dark, variant, opposite, apply, set, toggle }
})
