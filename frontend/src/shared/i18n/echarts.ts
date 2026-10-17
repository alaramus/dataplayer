import { registerLocale } from "echarts/core"
// ECharts writes month and day names and its own few words itself; its
// Russian is a module of its own, registered once.
import langRU from "echarts/lib/i18n/langRU.js"

import { currentLanguage } from "@/shared/i18n"
import type { Language } from "@/shared/i18n"

registerLocale("RU", langRU)

/** ECharts' own name for the interface's language (D227). */
const LOCALES: Record<Language, string> = { en: "EN", ru: "RU" }

/**
 * The locale to start a chart in. Read when a chart is made: one drawn before
 * a language switch keeps its axis words until it is drawn again.
 */
export function chartLocale(): string {
  return LOCALES[currentLanguage()]
}
