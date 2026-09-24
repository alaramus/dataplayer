import { describe, expect, it } from "vitest"

import { runDuration } from "./runDuration"

const started = "2026-09-24T12:00:00Z"
const run = { created_at: started, finished_at: null }
const start = Date.parse(started)

describe("agent run duration", () => {
  it("advances while the run record stays unchanged", () => {
    expect(runDuration(run, start)).toBe("0 s")
    expect(runDuration(run, start + 1_000)).toBe("1 s")
    expect(runDuration(run, start + 10_000)).toBe("10 s")
  })

  it("stays at the recorded finish after the run ends", () => {
    const finished = { ...run, finished_at: "2026-09-24T12:00:07Z" }
    expect(runDuration(finished, start + 60_000)).toBe("7 s")
  })

  it("waits for the start timestamp", () => {
    expect(runDuration({ created_at: null, finished_at: null }, start)).toBe("")
  })
})
