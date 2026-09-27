import { describe, expect, it } from "vitest"

import type { JobPublic } from "@/client"
import type { AttentionItem } from "@/shared/notifications"

import {
  arrivals, endedEntry, endingId, endings, isRecent, jobOfEnding, linesBeyond, RECENT_FOR, toldOnScreen,
} from "./endings"
import type { ProcessRow } from "./presentation"

function job(state: JobPublic["state"], extra: Partial<JobPublic> = {}): JobPublic {
  return {
    id: "j1",
    kind: "backup.create",
    subject_id: null,
    parameters: null,
    state,
    step: null,
    step_index: 0,
    step_count: 0,
    message: null,
    created_at: "2026-09-27T10:00:00Z",
    started_at: "2026-09-27T10:00:01Z",
    finished_at: "2026-09-27T10:00:09Z",
    ...extra,
  }
}

function row(detail: string): ProcessRow {
  return {
    id: "j1", source: "server", label: "Pipeline · Nightly", detail, status: "Completed", tone: "success",
    active: false, paused: false, progress: 1, measurement: "", createdAt: 0,
    canPause: false, canResume: false, canStop: false, controlsHint: "",
  }
}

function item(id: string, at: number): AttentionItem {
  return { id, tone: "error", title: id, detail: "", at, action: null, dismiss: null }
}

describe("what a job's ending becomes", () => {
  it("is one entry in Recent when it did what was asked, with the steps behind it", () => {
    const entry = endedEntry(
      job("succeeded", { message: "orders.csv saved" }),
      row("orders.csv saved\n1. Save as CSV — orders.csv saved")
    )

    expect(entry).toEqual({
      id: "job:j1",
      at: Date.parse("2026-09-27T10:00:09Z"),
      notice: {
        tone: "success",
        title: "Pipeline · Nightly",
        message: "orders.csv saved",
        // The message is said once, not again as the first of its lines.
        lines: ["1. Save as CSV — orders.csv saved"],
        action: null,
      },
    })
  })

  it("is news rather than a question when it was stopped on request", () => {
    expect(endedEntry(job("cancelled"), row(""))?.notice).toMatchObject({ tone: "info", message: "Completed" })
  })

  it("is nothing in Recent when it failed, which waits in Needs you instead", () => {
    expect(endedEntry(job("failed"), row(""))).toBeNull()
    expect(endedEntry(job("interrupted"), row(""))).toBeNull()
    expect(endedEntry(job("running"), row(""))).toBeNull()
  })

  it("is named in the log by its job, and found again by that name", () => {
    expect(jobOfEnding(endingId("j1"))).toBe("j1")
    expect(jobOfEnding("a-message")).toBeNull()
  })

  it("keeps only the lines that say something beyond the message", () => {
    expect(linesBeyond("done\n\n  1. step  \ndone", "done")).toEqual(["1. step"])
  })

  it("stays recent for a day after it ended, read again after a reload", () => {
    const ended = Date.parse("2026-09-27T10:00:09Z")
    expect(isRecent(job("succeeded"), ended + RECENT_FOR)).toBe(true)
    expect(isRecent(job("succeeded"), ended + RECENT_FOR + 1)).toBe(false)
    expect(isRecent(job("running", { finished_at: null }), ended)).toBe(false)
  })
})

describe("which endings happen while a tab watches", () => {
  it("is a job seen running that is over now", () => {
    const first = endings(new Set(), [job("running")])
    expect(first.ended).toEqual([])
    expect([...first.watched]).toEqual(["j1"])

    const second = endings(first.watched, [job("succeeded")])
    expect(second.ended.map((one) => one.state)).toEqual(["succeeded"])
    expect([...second.watched]).toEqual([])
  })

  it("is not a job found already over, after a reload", () => {
    expect(endings(new Set(), [job("failed")]).ended).toEqual([])
  })

  it("waits for a job started here that the listing does not hold yet", () => {
    // Started a moment ago: the next poll may not list it, and it must not be
    // forgotten before it has been seen to end.
    const waiting = endings(new Set(["j1"]), [])
    expect([...waiting.watched]).toEqual(["j1"])
    expect(endings(waiting.watched, [job("succeeded")]).ended).toHaveLength(1)
  })

  it("is not told on screen for a run its schedule started, which nobody waited for", () => {
    const step = {
      link_id: "link-1", title: "Save as CSV",
      source_label: "Sales · orders", target_label: "Files · reports",
      destination_connector_id: "files", changes_source: false,
      paste: { source_connector_id: "sales", source_node_ids: ["orders"], mode: "copy", kind: "relation_csv" },
      outcome: "done", message: null, transfer: null,
    }
    const run = (extra: Record<string, unknown>) => job("succeeded", {
      kind: "pipeline.run",
      parameters: { version: 1, pipeline_id: "p1", pipeline_name: "Nightly", steps: [step], ...extra },
    })
    const scheduled = run({ scheduled_for: "2026-09-27T10:00:00Z" })
    expect(toldOnScreen(run({}))).toBe(true)
    expect(toldOnScreen(job("succeeded"))).toBe(true)
    expect(toldOnScreen(scheduled)).toBe(false)
  })
})

describe("what is new in Needs you", () => {
  it("is what was not there before and happened after the page opened", () => {
    const opened = 1000
    const first = arrivals(new Set(), [item("old", 500), item("new", 1500)], opened)
    // Already waiting when the page opened: in the sheet and the count, not
    // announced again on every reload.
    expect(first.arrived.map((one) => one.id)).toEqual(["new"])

    const again = arrivals(first.known, [item("old", 500), item("new", 1500)], opened)
    expect(again.arrived).toEqual([])
  })
})
