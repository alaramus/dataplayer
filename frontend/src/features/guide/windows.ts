import { appIcons } from "@/shared/ui"
import { useWindowManager } from "@/shared/windows"
import type { OpenWindow } from "@/shared/windows"

import GuideWindow from "./GuideWindow.vue"
import { shownGuidePage } from "./state"

export const GUIDE_WINDOW_ID = "guide"

export function guideWindow(): OpenWindow {
  return {
    id: GUIDE_WINDOW_ID,
    look: { title: "Guide", icon: appIcons.menuBook },
    size: { width: 720, height: 680 },
    sizing: "stable",
    minSize: { width: 420, height: 320 },
    component: GuideWindow,
  }
}

/** Open the guide on one page, or turn the open guide to it. */
export function useOpenGuide(): (key: string) => void {
  const windows = useWindowManager()
  return (key) => {
    shownGuidePage.value = key
    windows.open(guideWindow())
  }
}
