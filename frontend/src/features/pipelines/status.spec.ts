import { describe, expect, it } from "vitest"

import { runsWords, statusLine } from "./status"

const NOW = Date.parse("2026-11-13T12:00:00Z")

describe("the status line at the foot of the canvas (D364)", () => {
  it("names the link that lacks a choice, and opens it", () => {
    const line = statusLine(
      { kind: "lacking", link_id: "l2", message: "2 · Add rows needs its columns paired", continuous: 1, scheduled: 1 },
      NOW
    )
    expect(line).toMatchObject({ tone: "caution", action: "link", linkId: "l2" })
    expect(line?.text).toBe("Not ready: 2 · Add rows needs its columns paired")
  })

  it("asks for a schedule when links run on one and none is set", () => {
    const line = statusLine({ kind: "no_schedule", continuous: 0, scheduled: 2 }, NOW)
    expect(line).toMatchObject({ tone: "caution", action: "schedule" })
    expect(line?.text).toBe("2 links run on the schedule, and no schedule is set")
  })

  it("says what switching on will do", () => {
    expect(statusLine({ kind: "ready", continuous: 2, scheduled: 0 }, NOW)?.text).toBe(
      "Ready. Switch on and 2 links run continuously"
    )
    expect(runsWords(2, 1)).toBe("2 links run continuously, 1 link runs on the schedule")
  })

  it("says how long it has been on, when it last carried and when the schedule comes next", () => {
    const line = statusLine(
      {
        kind: "on",
        continuous: 1,
        scheduled: 1,
        since: "2026-11-13T11:46:00Z",
        last_at: "2026-11-13T11:59:58Z",
        next_at: "2026-11-13T15:00:00Z",
      },
      NOW
    )
    expect(line).toMatchObject({ tone: "working", action: "history" })
    // Today or tomorrow, as the zone the test runs in puts 15:00 UTC.
    expect(line?.text).toMatch(/^On for 14m · last carried 2s ago · next run (today|tomorrow) /)
  })

  it("says a failing link is tried again, and nothing before the first answer", () => {
    expect(statusLine({ kind: "retrying", link_id: "l1", message: "The broker is away" }, NOW)).toMatchObject({
      tone: "caution",
      action: "link",
      linkId: "l1",
      text: "A link is failing and is tried again: The broker is away",
    })
    expect(statusLine(undefined, NOW)).toBeNull()
  })
})
