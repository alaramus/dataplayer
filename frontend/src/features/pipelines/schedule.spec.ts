import { describe, expect, it } from "vitest"

import { firstSettings, intervalParts, minutesOf, nextRunWords, scheduleWords } from "./schedule"

describe("a pipeline's schedule on the screen (D179)", () => {
  it("says what a schedule does in a line", () => {
    const nightly = { ...firstSettings("Europe/Riga"), enabled: true }
    expect(scheduleWords(nightly)).toBe("Every day at 03:00")
    expect(scheduleWords({ ...nightly, times: ["18:00", "09:00"], days: [0, 1, 2, 3, 4] }))
      .toBe("Weekdays at 09:00 and 18:00")
    expect(scheduleWords({ ...nightly, days: [5, 6] })).toBe("Weekends at 03:00")
    expect(scheduleWords({ ...nightly, days: [0, 2] })).toBe("Mon, Wed at 03:00")
    expect(scheduleWords({ ...nightly, kind: "interval", every_minutes: 5 })).toBe("Every 5 minutes")
    expect(scheduleWords({ ...nightly, kind: "interval", every_minutes: 60 })).toBe("Every hour")
    expect(scheduleWords({ ...nightly, kind: "interval", every_minutes: 2 * 24 * 60 })).toBe("Every 2 days")
    expect(scheduleWords({ ...nightly, enabled: false })).toBe("Runs only when Run is pressed")
    expect(scheduleWords(null)).toBe("Runs only when Run is pressed")
  })

  it("shows an interval in the largest unit it fills, and back", () => {
    expect(intervalParts(90)).toEqual({ count: 90, unit: "minutes" })
    expect(intervalParts(120)).toEqual({ count: 2, unit: "hours" })
    expect(intervalParts(2880)).toEqual({ count: 2, unit: "days" })
    expect(minutesOf(3, "hours")).toBe(180)
  })

  it("says when it runs next in this browser's clock", () => {
    const now = new Date(2026, 8, 26, 12, 0).getTime()
    const at = (day: number, hour: number) => new Date(2026, 8, day, hour, 0).toISOString()
    expect(nextRunWords(at(26, 18), now)).toBe("today 18:00")
    expect(nextRunWords(at(27, 3), now)).toBe("tomorrow 03:00")
    expect(nextRunWords(at(29, 9), now)).toBe("Tue 09:00")
    expect(nextRunWords(new Date(2026, 9, 10, 3, 0).toISOString(), now)).toBe("10 Oct 03:00")
    expect(nextRunWords(null, now)).toBeNull()
  })
})
