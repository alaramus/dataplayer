import { describe, expect, it } from "vitest"

import { isJobEvent, isWorking, progressOf, touchesConnectors } from "./jobs"
import type { JobEvent } from "./jobs"

function event(overrides: Partial<JobEvent> = {}): JobEvent {
  return {
    job_id: "j1",
    kind: "service.create",
    subject_id: "s1",
    state: "running",
    step: "pulling the image",
    step_index: 1,
    step_count: 5,
    message: null,
    ...overrides,
  }
}

describe("what a job event is", () => {
  it("recognises one", () => {
    expect(isJobEvent(event())).toBe(true)
  })

  it("refuses anything else on the socket", () => {
    expect(isJobEvent({ connector_id: "c1", result: {} })).toBe(false)
    expect(isJobEvent(null)).toBe(false)
    expect(isJobEvent("jobs")).toBe(false)
  })
})

describe("what has to be read again", () => {
  it("re-reads the connections when a service job finished", () => {
    expect(touchesConnectors(event({ state: "succeeded" }))).toBe(true)
  })

  it("does not while it is still going", () => {
    expect(touchesConnectors(event({ state: "running" }))).toBe(false)
  })

  it("does not for a failure: nothing was made", () => {
    expect(touchesConnectors(event({ state: "failed" }))).toBe(false)
  })
})

describe("how far it has got", () => {
  it("says the step the server named, and its place", () => {
    expect(
      progressOf({
        state: "running",
        step: "pulling the image",
        step_index: 1,
        step_count: 5,
        message: null,
      })
    ).toBe("pulling the image (1 of 5)")
  })

  it("never invents a percentage", () => {
    const shown = progressOf({
      state: "running",
      step: "creating the container",
      step_index: 2,
      step_count: 5,
      message: null,
    })

    expect(shown).not.toContain("%")
  })

  it("says starting before a step has been reached", () => {
    expect(
      progressOf({
        state: "running",
        step: null,
        step_index: 0,
        step_count: 5,
        message: null,
      })
    ).toBe("Starting")
  })

  it("shows the outcome once there is one", () => {
    expect(
      progressOf({
        state: "failed",
        step: "pulling the image",
        step_index: 1,
        step_count: 5,
        message: "The image could not be fetched",
      })
    ).toBe("The image could not be fetched")
  })

  it("has nothing to say about a service that has no job", () => {
    expect(progressOf(null)).toBe("")
    expect(progressOf(undefined)).toBe("")
  })
})

describe("whether something is still happening", () => {
  it("is true while it runs and false once it has ended", () => {
    expect(isWorking({ state: "queued" })).toBe(true)
    expect(isWorking({ state: "running" })).toBe(true)
    expect(isWorking({ state: "succeeded" })).toBe(false)
    expect(isWorking({ state: "failed" })).toBe(false)
    expect(isWorking({ state: "interrupted" })).toBe(false)
    expect(isWorking(null)).toBe(false)
  })
})
