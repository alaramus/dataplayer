import type { WindowAction } from "./useWindows"
import { appIcons } from "@/shared/ui/icons"

/**
 * The command a window declares when what it holds can live as a workspace tab
 * (D155). Pressing it is a move, not a copy: the feature's `run` opens the tab
 * and closes the window, and the engine knows nothing about either side.
 */
export function openAsTabAction(run: () => void): WindowAction {
  return { icon: appIcons.tab, tooltip: "Open as a tab", testid: "window-to-tab", run }
}
