import { describe, expect, it } from "vitest"

import type { StoreStatus } from "@/client"

import { readStat } from "./statReading"
import { setupStage } from "./setupStage"

function status(partial: Partial<StoreStatus>): StoreStatus {
  return { state: "not_configured", may_set_up: false, ...partial }
}

describe("what the card says before there is a store", () => {
  it("tells somebody who cannot set it up who does", () => {
    expect(setupStage(status({}))).toEqual({ kind: "wait" })
  })

  it("offers a superuser both ways, and says why starting is off", () => {
    expect(setupStage(status({ may_set_up: true, start: { available: true } }))).toEqual({
      kind: "offer",
      canStart: true,
      startReason: null,
    })
    expect(
      setupStage(status({ may_set_up: true, start: { available: false, reason: "Services are off" } }))
    ).toEqual({ kind: "offer", canStart: false, startReason: "Services are off" })
  })

  it("shows the step a start has reached", () => {
    const stage = setupStage(
      status({
        state: "starting",
        may_set_up: true,
        job: {
          id: "j", kind: "metrics.store.create", subject_id: "s", parameters: null,
          state: "running", step: "pulling the image", step_index: 2, step_count: 6,
          message: null, created_at: "", started_at: null, finished_at: null,
        },
      })
    )

    expect(stage).toEqual({ kind: "starting", step: "Now pulling the image", progress: 2 / 6 })
  })

  it("says a failure and offers to start again only to a superuser who can", () => {
    expect(
      setupStage(status({ state: "failed", may_set_up: true, start: { available: true }, message: "pull failed" }))
    ).toEqual({ kind: "trouble", message: "The metrics store could not be started: pull failed", canStart: true })
    expect(setupStage(status({ state: "unreachable", may_set_up: true, start: { available: true } }))).toMatchObject({
      kind: "trouble",
      canStart: false,
    })
  })
})

describe("what a tile reads", () => {
  it("is the last value, and for seconds the moment the count started", () => {
    expect(readStat([[100, 10], [130, 40]], "s")).toEqual({ value: 40, at: 130, since: 90, restarted: false })
  })

  it("notices a counter that fell inside the range", () => {
    expect(readStat([[100, 500], [130, 5]], "s")?.restarted).toBe(true)
  })

  it("has nothing to say about no points, and no moment for other units", () => {
    expect(readStat([], "s")).toBeNull()
    expect(readStat([[1, 3]], "%")?.since).toBeNull()
  })
})
