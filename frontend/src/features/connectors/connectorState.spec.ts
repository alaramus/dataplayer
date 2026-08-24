import { describe, expect, it } from "vitest"

import { ageInWords, describeState } from "@/features/connectors/connectorState"
import type { CheckReport } from "@/stores/connectorChecks"

const NOW = Date.parse("2026-08-24T12:00:00Z")

function report(ok: boolean, checkedAt = "2026-08-24T12:00:00Z"): CheckReport {
  return { ok, message: ok ? "Connected" : "Refused", latencyMs: 3, checkedAt }
}

describe("what state a connection is in", () => {
  it("says nothing was checked when nothing was", () => {
    expect(describeState(true, null, NOW)).toEqual({
      state: "unknown",
      words: "Not checked yet",
    })
  })

  it("passes on what the last answer said", () => {
    expect(describeState(true, report(true), NOW).state).toBe("ok")
    expect(describeState(true, report(false), NOW).state).toBe("failed")
  })

  it("lets being switched off win over anything remembered", () => {
    expect(describeState(false, report(true), NOW)).toEqual({
      state: "disabled",
      words: "Switched off",
    })
  })

  // The ordinary case: a connection switched off before it was ever probed.
  // With the two rules the other way round this reads as "not checked yet",
  // which says nothing about why nobody is checking it.
  it("says switched off even when nothing was ever checked", () => {
    expect(describeState(false, null, NOW).state).toBe("disabled")
  })

  it("says how long ago the answer was given", () => {
    const described = describeState(true, report(true, "2026-08-24T11:58:00Z"), NOW)
    expect(described.words).toBe("Connected · 2 min ago")
  })
})

describe("how long ago", () => {
  it("counts seconds under a minute", () => {
    expect(ageInWords("2026-08-24T11:59:30Z", NOW)).toBe("30s ago")
  })

  it("counts minutes under an hour", () => {
    expect(ageInWords("2026-08-24T11:20:00Z", NOW)).toBe("40 min ago")
  })

  it("counts hours beyond that", () => {
    expect(ageInWords("2026-08-24T09:00:00Z", NOW)).toBe("3 h ago")
  })

  // A clock that is a little ahead of the server must not read as the future.
  it("never counts backwards", () => {
    expect(ageInWords("2026-08-24T12:00:05Z", NOW)).toBe("0s ago")
  })
})
