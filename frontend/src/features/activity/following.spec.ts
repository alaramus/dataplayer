import { describe, expect, it } from "vitest"
import { ref } from "vue"

import type { JobPublic } from "@/client"

import { carriedOf, followingAttention, followOf, NEEDS_YOU_AFTER } from "./following"
import { serverRow } from "./presentation"

function job(links: Array<Record<string, unknown>>, state: JobPublic["state"] = "running"): JobPublic {
  return {
    id: "j1",
    kind: "pipeline.follow",
    subject_id: "p1",
    parameters: { version: 1, pipeline_id: "p1", pipeline_name: "Nightly", links },
    state,
    step: "following its topics",
    step_index: 1,
    step_count: 1,
    message: null,
    created_at: "2026-11-08T12:00:00Z",
    started_at: "2026-11-08T12:00:00Z",
    finished_at: null,
  } as JobPublic
}

const quiet = { link_id: "l1", title: "Orders", carried: 12, failures: 0, last_error: null, state: "idle" }
const failing = { link_id: "l2", title: "Prices", carried: 3, failures: NEEDS_YOU_AFTER, last_error: "Kafka is away", state: "retrying" }

describe("a following in the footer and in Needs you (D315)", () => {
  it("reads the follower's record", () => {
    const record = followOf(job([quiet, failing]))
    expect(record?.pipelineName).toBe("Nightly")
    expect(record && carriedOf(record)).toBe(15)
    expect(followOf({ ...job([]), kind: "pipeline.run" })).toBeNull()
  })

  it("is a row named by its pipeline, with what it carried, and Stop", () => {
    const row = serverRow(job([quiet]), undefined)
    expect(row.label).toBe("Nightly · following · links: 1")
    expect(row.brief).toBe("Messages carried: 12")
    expect(row.canStop).toBe(true)
  })

  it("makes a link failing ten times in a row an item, only while it follows", () => {
    const items = followingAttention(ref([job([quiet, failing])]))
    expect(items.value.map((item) => item.title)).toEqual(["Nightly: Prices keeps failing"])
    expect(items.value[0]?.dismiss).toBeNull()
    expect(followingAttention(ref([job([failing], "cancelled")])).value).toEqual([])
  })
})
