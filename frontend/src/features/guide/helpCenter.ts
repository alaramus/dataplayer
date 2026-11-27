import { onBeforeUnmount, provide, watch } from "vue"

import { helpCenterKey } from "@/shared/help"
import { t } from "@/shared/i18n"
import { keysOf, onMac, registerShortcut } from "@/shared/keys/shortcuts"
import type { WindowsApi } from "@/shared/windows"

import { openGuide } from "./windows"

/** The key that opens the Help Center: the one every program opens help with. */
export const HELP_KEY = "F1"

/**
 * The Help Center for the whole application: the user menu's line, given to
 * the kit's layout, and F1, answered while somebody is signed in — the guide
 * is theirs to read and nobody else's.
 */
export function useHelpCenter(windows: WindowsApi, signedIn: () => boolean): void {
  const open = () => { openGuide(windows) }
  provide(helpCenterKey, { open, keys: keysOf(HELP_KEY, onMac()) })

  let unregister: (() => void) | null = null
  watch(
    signedIn,
    (now) => {
      unregister?.()
      unregister = null
      if (!now) return
      unregister = registerShortcut({
        id: "help-center",
        key: HELP_KEY,
        // A getter, so the scene lists it in the language current when shown.
        get action() { return t("onboarding.guide.open") },
        run: open,
      })
    },
    { immediate: true }
  )
  onBeforeUnmount(() => unregister?.())
}
