import { describe, expect, it } from "vitest"

import type { JobPublic } from "@/client"

import { isRunning, lifecycleCommand } from "./lifecycle"

type Row = Parameters<typeof lifecycleCommand>[0]

function service(overrides: Partial<Row> = {}): Row {
  return {
    state: "running",
    container_state: "running",
    was_connected: true,
    job: null,
    ...overrides,
  }
}

function job(state: JobPublic["state"]): JobPublic {
  return {
    id: "j1",
    kind: "service.stop",
    subject_id: "s1",
    parameters: null,
    state,
    step: null,
    step_index: 0,
    step_count: 1,
    message: null,
    created_at: "2026-09-18T00:00:00Z",
    started_at: null,
    finished_at: null,
  }
}

describe("whether a service can be stopped or started", () => {
  it("offers a stop for a running one and a start for a stopped one", () => {
    expect(lifecycleCommand(service())).toBe("stop")
    expect(
      lifecycleCommand(service({ state: "stopped", container_state: "stopped" }))
    ).toBe("start")
  })

  it("goes by the container when the row believes otherwise", () => {
    // Stopped by hand outside this application.
    expect(lifecycleCommand(service({ container_state: "stopped" }))).toBe("start")
    // A stop that failed leaves the row failed with the container still up.
    expect(lifecycleCommand(service({ state: "failed" }))).toBe("stop")
  })

  it("offers nothing without a container to act on", () => {
    expect(lifecycleCommand(service({ container_state: "missing" }))).toBeNull()
    expect(lifecycleCommand(service({ container_state: "unknown" }))).toBeNull()
  })

  it("offers nothing while something is being done to it", () => {
    expect(lifecycleCommand(service({ job: job("running") }))).toBeNull()
    expect(lifecycleCommand(service({ job: job("queued") }))).toBeNull()
    expect(lifecycleCommand(service({ job: job("succeeded") }))).toBe("stop")
    expect(lifecycleCommand(service({ state: "creating" }))).toBeNull()
    expect(lifecycleCommand(service({ state: "removing" }))).toBeNull()
  })

  it("offers nothing to a creation that never became a connection", () => {
    expect(
      lifecycleCommand(service({ state: "failed", was_connected: false }))
    ).toBeNull()
  })
})

describe("whether a service is running", () => {
  it("is what the runtime says of its container", () => {
    expect(isRunning(service())).toBe(true)
    expect(isRunning(service({ container_state: "stopped" }))).toBe(false)
    // Stopped or removed by hand: the row still believes it runs.
    expect(isRunning(service({ container_state: "missing" }))).toBe(false)
  })

  it("is what the row believes when the runtime could not be asked", () => {
    expect(isRunning(service({ container_state: "unknown" }))).toBe(true)
    expect(isRunning(service({ state: "stopped", container_state: "unknown" }))).toBe(false)
  })
})
