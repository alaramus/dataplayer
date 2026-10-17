import { afterEach, describe, expect, it } from "vitest"

import { applyLanguage } from "@/shared/i18n"
import { timeTick } from "./chartOption"

afterEach(async () => {
  await applyLanguage("en")
})

describe("a tick on the time axis", () => {
  it("says a date at midnight rather than a bare day", async () => {
    await applyLanguage("ru")
    expect(timeTick(new Date(2026, 9, 18, 0, 0).getTime())).toBe("18 окт.")
    await applyLanguage("en")
    expect(timeTick(new Date(2026, 9, 18, 0, 0).getTime())).toBe("Oct 18")
  })

  it("says hours and minutes on a 24-hour clock in either language", async () => {
    expect(timeTick(new Date(2026, 9, 17, 23, 56).getTime())).toBe("23:56")
    await applyLanguage("ru")
    expect(timeTick(new Date(2026, 9, 17, 23, 56).getTime())).toBe("23:56")
  })

  it("adds the seconds only when the tick falls between minutes", () => {
    expect(timeTick(new Date(2026, 9, 17, 23, 56, 30).getTime())).toBe("23:56:30")
  })
})
