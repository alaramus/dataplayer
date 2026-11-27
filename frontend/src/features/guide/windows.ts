import { t } from "@/shared/i18n"
import { appIcons } from "@/shared/ui"
import { useWindowManager } from "@/shared/windows"
import type { OpenWindow, WindowsApi } from "@/shared/windows"

import GuideWindow from "./GuideWindow.vue"
import { shownGuidePage } from "./state"

export const GUIDE_WINDOW_ID = "guide"

export function guideWindow(): OpenWindow {
  return {
    id: GUIDE_WINDOW_ID,
    look: { title: t("onboarding.guide.help_center"), icon: appIcons.menuBook },
    size: { width: 900, height: 680 },
    sizing: "stable",
    minSize: { width: 600, height: 360 },
    component: GuideWindow,
  }
}

/** Open the Help Center, on one page or on the page last read. */
export function openGuide(windows: WindowsApi, key?: string): void {
  if (key !== undefined) shownGuidePage.value = key
  windows.open(guideWindow())
}

/** Open the guide on one page, or turn the open guide to it. */
export function useOpenGuide(): (key: string) => void {
  const windows = useWindowManager()
  return (key) => { openGuide(windows, key) }
}
