import { onBeforeUnmount, onMounted, ref } from "vue"

/**
 * The page filling the screen, as the browser's own Fullscreen API sees it.
 *
 * The unprefixed API only, which every desktop browser this application is
 * used from has: the prefixed spellings would cost casts through `unknown`,
 * since TypeScript's DOM library does not describe them.
 *
 * F11 is a different thing that looks the same — the browser's own fullscreen,
 * outside the API. It sets no `fullscreenElement` and fires no
 * `fullscreenchange`, so nothing here can follow it.
 */
export function useFullscreen() {
  /**
   * The browser is the source of truth, not this flag: leaving fullscreen with
   * Escape tells no button it was pressed, so the event is what updates it.
   */
  const active = ref(Boolean(document.fullscreenElement))
  const supported = typeof document.documentElement.requestFullscreen === "function"

  function sync() {
    active.value = Boolean(document.fullscreenElement)
  }

  onMounted(() => document.addEventListener("fullscreenchange", sync))
  onBeforeUnmount(() => document.removeEventListener("fullscreenchange", sync))

  async function toggle() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else await document.documentElement.requestFullscreen()
    } catch {
      /* The browser refused — a request outside a user gesture, or a policy
         forbidding it. There is nothing to undo: `active` follows the event,
         which did not arrive. */
    }
  }

  return { active, supported, toggle }
}
