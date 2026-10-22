import { registerLocale } from "echarts/core"
// ECharts writes month and day names and its own few words itself; its
// Russian, German, French and Chinese are modules of their own, registered once.
import langDE from "echarts/lib/i18n/langDE.js"
import langFR from "echarts/lib/i18n/langFR.js"
import langRU from "echarts/lib/i18n/langRU.js"
import langZH from "echarts/lib/i18n/langZH.js"

import { currentLanguage } from "@/shared/i18n"
import type { Language } from "@/shared/i18n"

registerLocale("RU", langRU)
registerLocale("DE", langDE)
registerLocale("FR", langFR)
registerLocale("ZH", langZH)

/**
 * ECharts' own name for the interface's language (D227). ECharts ships no
 * Hindi pack, so its own words stay English there.
 */
const LOCALES: Record<Language, string> = { en: "EN", ru: "RU", de: "DE", fr: "FR", zh: "ZH", hi: "EN" }

/**
 * The locale to start a chart in. Read when a chart is made: one drawn before
 * a language switch keeps its axis words until it is drawn again.
 */
export function chartLocale(): string {
  return LOCALES[currentLanguage()]
}
