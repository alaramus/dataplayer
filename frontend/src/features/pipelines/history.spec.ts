import { describe, expect, it } from "vitest"

import type { PipelineRunPublic } from "@/client"

import { historyLine, momentWords, shownWords } from "./history"
import type { HistoryRow } from "./history"

const at = (day: number, hour: number, minute = 0, second = 0) =>
  new Date(2026, 8, day, hour, minute, second).toISOString()
const now = new Date(2026, 8, 27, 12, 0).getTime()

function run(fields: Partial<Extract<HistoryRow, { kind: "run" }>>): HistoryRow {
  return {
    kind: "run", job_id: "j1", state: "succeeded", message: "All 3 links ran",
    started_at: at(26, 3), finished_at: at(26, 3, 0, 12), scheduled: false, ...fields,
  }
}

describe("a pipeline's history on the screen (D180)", () => {
  it("says when in this browser's clock, the year only when it is another", () => {
    expect(momentWords(at(26, 3), now)).toBe("26 Sep 03:00")
    expect(momentWords(new Date(2025, 11, 31, 23, 5).toISOString(), now)).toBe("31 Dec 2025 23:05")
  })

  it("says of a run its sentence, when, who started it and how long it took", () => {
    expect(historyLine(run({}), now)).toEqual({
      key: "j1", jobId: "j1", said: "All 3 links ran", detail: "26 Sep 03:00 · by hand · took 12.0 s", tone: "plain",
    })
    const scheduled = historyLine(run({ scheduled: true, finished_at: at(26, 3, 2, 5) }), now)
    expect(scheduled.detail).toBe("26 Sep 03:00 · by the schedule · took 2m 5s")
  })

  it("puts a run that failed or was cut short in the caution colour", () => {
    const failed = historyLine(run({ state: "failed", message: "Stopped at 2 of 3, Save as CSV: taken" }), now)
    expect([failed.said, failed.tone]).toEqual(["Stopped at 2 of 3, Save as CSV: taken", "caution"])
    const cut = historyLine(run({ state: "interrupted", message: null }), now)
    expect([cut.said, cut.tone]).toEqual(["Interrupted", "caution"])
    expect(historyLine(run({ state: "cancelled", message: "Stopped on request" }), now).tone).toBe("plain")
  })

  it("says how long a run going has gone so far", () => {
    const going = historyLine(run({ state: "running", message: null, started_at: at(27, 11, 59, 30), finished_at: null }), now)
    expect([going.said, going.detail]).toEqual(["Running", "27 Sep 11:59 · by hand · 30.0 s so far"])
    const queued = historyLine(run({ state: "queued", message: null, finished_at: null }), now)
    expect([queued.said, queued.detail]).toEqual(["Waiting to start", "26 Sep 03:00 · by hand"])
  })

  it("says a skip and a miss as rows that show no run", () => {
    const skipped: HistoryRow = { kind: "skipped", at: at(26, 4), reason: "the previous run was still going" }
    expect(historyLine(skipped, now)).toEqual({
      key: `skipped:${at(26, 4)}`, jobId: null, said: "Skipped: the previous run was still going",
      detail: "26 Sep 04:00 · by the schedule", tone: "muted",
    })
    const missed: HistoryRow = { kind: "missed", at: at(26, 5), reason: "the server was off" }
    expect(historyLine(missed, now).said).toBe("Missed: the server was off")
  })

  it("names the run shown over the canvas by when it started", () => {
    const shown: PipelineRunPublic = {
      job_id: "j1", state: "succeeded", message: null, started_at: at(26, 3), finished_at: at(26, 3, 1), links: [],
    }
    expect(shownWords(shown, now)).toBe("Showing the run of 26 Sep 03:00")
  })
})
