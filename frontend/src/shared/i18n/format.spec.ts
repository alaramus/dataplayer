import { afterEach, describe, expect, it } from "vitest"

import { applyLanguage } from "@/shared/i18n"
import { formatDate, formatDateTime, formatFixed, formatNumber, formatTime } from "@/shared/i18n/format"

// A fixed moment read in UTC, so the machine's own zone does not move it.
const MOMENT = Date.UTC(2026, 9, 17, 15, 4, 5)
const UTC = { timeZone: "UTC" } as const

// Russian groups thousands with a no-break space, which a test reads as a space.
const spaced = (text: string) => text.replace(/\s/gu, " ")

afterEach(async () => {
  await applyLanguage("en")
  localStorage.clear()
})

describe("format", () => {
  it("writes dates in English by default", () => {
    expect(formatDateTime(MOMENT, UTC)).toBe("10/17/2026, 3:04:05 PM")
    expect(formatDate(MOMENT, UTC)).toBe("10/17/2026")
    expect(formatTime(new Date(MOMENT), UTC)).toBe("3:04:05 PM")
    expect(formatDateTime(new Date(MOMENT).toISOString(), UTC)).toBe("10/17/2026, 3:04:05 PM")
  })

  it("writes dates in Russian when the interface speaks it", async () => {
    await applyLanguage("ru")
    expect(formatDateTime(MOMENT, UTC)).toBe("17.10.2026, 15:04:05")
    expect(formatDate(MOMENT, UTC)).toBe("17.10.2026")
    expect(formatTime(MOMENT, UTC)).toBe("15:04:05")
  })

  it("writes dates in German when the interface speaks it", async () => {
    await applyLanguage("de")
    expect(formatDateTime(MOMENT, UTC)).toBe("17.10.2026, 15:04:05")
    expect(formatDate(MOMENT, UTC)).toBe("17.10.2026")
    expect(formatTime(MOMENT, UTC)).toBe("15:04:05")
  })

  it("writes numbers in the interface's language", async () => {
    expect(formatNumber(4211.5)).toBe("4,211.5")
    expect(formatFixed(4.25, 1)).toBe("4.3")
    expect(formatFixed(12345.678, 2)).toBe("12345.68")
    await applyLanguage("ru")
    expect(spaced(formatNumber(4211.5))).toBe("4 211,5")
    expect(formatFixed(4.2, 1)).toBe("4,2")
    expect(formatFixed(12345.678, 2)).toBe("12345,68")
    await applyLanguage("de")
    expect(spaced(formatNumber(4211.5))).toBe("4.211,5")
    expect(formatFixed(4.2, 1)).toBe("4,2")
    expect(formatFixed(12345.678, 2)).toBe("12345,68")
  })
})
