import { defineStore } from "pinia"
import { Dark } from "quasar"
import { computed, ref, watch } from "vue"

export const THEME_KEY = "dataplayer-theme"

/**
 * Light, dark, a named dark ground, or whatever the system says. Pinia,
 * because the server knows nothing about it (D6). System is the default and
 * a choice of its own: a person who picked Light can go back to following
 * the machine, whose theme may change at sunset while the page stays open.
 *
 * The one place that names Quasar's Dark plugin. It puts `body--dark` on the
 * document and `shared/ui/theme.css` hangs every colour of ours off the same
 * class, so the kit and the screens turn over on one event rather than two.
 * A named ground is a theme with its own palette: `body--dark` stays on
 * for the dark ones, while paper-light carries the marker without it, and
 * a `data-dp-theme` marker selects the palette either way.
 */
export type ThemeMode =
  | "light"
  | "dark"
  | "dark-blue"
  | "paper"
  | "midnight"
  | "dark-purple"
  | "paper-light"
  | "system"

/**
 * A theme with its own palette, or nothing for the two plain ones. The
 * marker rides beside Quasar's dark class, on or off: paper-light is a
 * light theme carrying it without `body--dark`.
 */
export type ThemeVariant = "dark-blue" | "paper" | "midnight" | "dark-purple" | "paper-light" | null

const QUERY = "(prefers-color-scheme: dark)"

/** What the browser was told to prefer. */
export function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(QUERY).matches
}

function chosen(): ThemeMode {
  const found = localStorage.getItem(THEME_KEY)
  return found === "dark" ||
    found === "dark-blue" ||
    found === "paper" ||
    found === "midnight" ||
    found === "dark-purple" ||
    found === "paper-light" ||
    found === "light"
    ? found
    : "system"
}

export const useThemeStore = defineStore("theme", () => {
  const mode = ref<ThemeMode>(chosen())
  const systemDark = ref(systemPrefersDark())
  const dark = computed(() =>
    mode.value === "system"
      ? systemDark.value
      : mode.value !== "light" && mode.value !== "paper-light"
  )
  const variant = computed<ThemeVariant>(() =>
    mode.value === "dark-blue" ||
    mode.value === "paper" ||
    mode.value === "midnight" ||
    mode.value === "dark-purple" ||
    mode.value === "paper-light"
      ? mode.value
      : null
  )

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
   * Called from `main.ts` before the application is mounted: applied
   * afterwards, the first frame is light and a dark theme opens with a flash
   * of the other one.
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
    if (value === "system") localStorage.removeItem(THEME_KEY)
    else localStorage.setItem(THEME_KEY, value)
  }

  /**
   * The other of the two plain themes, chosen outright, whatever answered
   * before. A named ground is left for Preferences: the toggle only ever
   * lands on light or dark, so from one it lands on light.
   */
  function toggle() {
    set(dark.value ? "light" : "dark")
  }

  return { mode, dark, variant, apply, set, toggle }
})
