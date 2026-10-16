import type { WindowAction } from "./useWindows"
import { t } from "@/shared/i18n"
import { appIcons } from "@/shared/ui/icons"

/**
 * The command a window declares when what it holds can live as a workspace tab
 * (D155). Pressing it is a move, not a copy: the feature's `run` opens the tab
 * and closes the window, and the engine knows nothing about either side.
 */
export function openAsTabAction(run: () => void): WindowAction {
  return {
    icon: appIcons.tab,
    // A getter, so a window opened before a language switch follows it.
    get tooltip() {
      return t("windows.open_as_tab")
    },
    testid: "window-to-tab",
    run,
  }
}
