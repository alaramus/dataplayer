import { afterEach, describe, expect, it } from "vitest"

import { applyLanguage } from "@/shared/i18n"

import { chartLocale } from "./echarts"

afterEach(async () => {
  await applyLanguage("en")
  localStorage.clear()
})

describe("the language a chart starts in", () => {
  it("is ECharts' name for the interface's language", async () => {
    expect(chartLocale()).toBe("EN")

    await applyLanguage("ru")
    expect(chartLocale()).toBe("RU")

    await applyLanguage("de")
    expect(chartLocale()).toBe("DE")

    await applyLanguage("ar")
    expect(chartLocale()).toBe("AR")
  })
})
