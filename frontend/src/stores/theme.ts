import { defineStore } from "pinia"
import { Dark } from "quasar"
import { computed, ref, watch } from "vue"

export const THEME_KEY = "dataplayer-theme"

/**
 * Light, dark, or whatever the system says. Pinia, because the server knows
 * nothing about it (D6). System is the default and a choice of its own: a
 * person who picked Light can go back to following the machine, whose theme
 * may change at sunset while the page stays open.
 *
 * The one place that names Quasar's Dark plugin. It puts `body--dark` on the
 * document and `shared/ui/theme.css` hangs every colour of ours off the same
 * class, so the kit and the screens turn over on one event rather than two.
 */
export type ThemeMode = "light" | "dark" | "system"

const QUERY = "(prefers-color-scheme: dark)"

/** What the browser was told to prefer. */
export function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(QUERY).matches
}

function chosen(): ThemeMode {
  const found = localStorage.getItem(THEME_KEY)
  return found === "dark" || found === "light" ? found : "system"
}

export const useThemeStore = defineStore("theme", () => {
  const mode = ref<ThemeMode>(chosen())
  const systemDark = ref(systemPrefersDark())
  const dark = computed(() => (mode.value === "system" ? systemDark.value : mode.value === "dark"))

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
  }
  watch(dark, apply, { flush: "sync" })

  function set(value: ThemeMode) {
    mode.value = value
    // Nothing stored is System, so an old browser and a new choice agree.
    if (value === "system") localStorage.removeItem(THEME_KEY)
    else localStorage.setItem(THEME_KEY, value)
  }

  /** The other of the two themes, chosen outright, whatever answered before. */
  function toggle() {
    set(dark.value ? "light" : "dark")
  }

  return { mode, dark, apply, set, toggle }
})
