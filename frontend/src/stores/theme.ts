import { defineStore } from "pinia"
import { Dark } from "quasar"
import { ref } from "vue"

export const THEME_KEY = "dataplayer-theme"

/**
 * Light or dark, and where that is decided.
 *
 * Pinia, because the server knows nothing about it — D6. Two states and not
 * three: "as the system says" is what answers before anything has been
 * chosen, and a menu offering it back would be a third state whose only job
 * is to return to the default.
 *
 * This is the one place that names Quasar's Dark plugin. It puts `body--dark`
 * on the document, and `shared/ui/theme.css` hangs every colour of our own
 * off the same class — so the components of the kit and the colours the
 * screens draw themselves with turn over on one event rather than two.
 */

/** What the browser was told to prefer, asked only when nothing was chosen. */
export function systemPrefersDark(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  )
}

function chosen(): boolean | null {
  const found = localStorage.getItem(THEME_KEY)
  if (found === "dark") return true
  if (found === "light") return false
  return null
}

export const useThemeStore = defineStore("theme", () => {
  const dark = ref(chosen() ?? systemPrefersDark())

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

  function set(value: boolean) {
    dark.value = value
    localStorage.setItem(THEME_KEY, value ? "dark" : "light")
    apply()
  }

  function toggle() {
    set(!dark.value)
  }

  return { dark, apply, set, toggle }
})
