import { describe, expect, it } from "vitest"
import { ref } from "vue"

import type { JobPublic } from "@/client"
import { ranked } from "@/shared/notifications"
import type { AttentionItem } from "@/shared/notifications"
import { isOutstanding, outstandingJobs } from "./attention"

function job(state: JobPublic["state"], extra: Partial<JobPublic> = {}): JobPublic {
  return {
    id: `job-${state}-${extra.message ?? ""}`,
    kind: "backup.create",
    subject_id: null,
    parameters: null,
    state,
    step: "writing the file",
    step_index: 2,
    step_count: 3,
    message: null,
    created_at: "2026-09-06T10:00:00Z",
    started_at: "2026-09-06T10:00:01Z",
    finished_at: "2026-09-06T10:00:09Z",
    ...extra,
  }
}

function item(tone: AttentionItem["tone"], at: number): AttentionItem {
  return { id: `${tone}${at}`, tone, title: tone, detail: "", at, action: null, dismiss: null }
}

describe("which jobs are somebody's business", () => {
  it("is the ones that ended without doing what was asked", () => {
    expect(["failed", "interrupted"].map((state) => isOutstanding(job(state as JobPublic["state"]))))
      .toEqual([true, true])
    expect(["queued", "running", "succeeded", "cancelled"].map(
      (state) => isOutstanding(job(state as JobPublic["state"]))
    )).toEqual([false, false, false, false])
  })

  it("says what a restart left behind, which nothing said before", () => {
    const jobs = ref([job("interrupted")])
    const items = outstandingJobs(jobs, () => ({ label: "Create backup", lines: [] }), ref(new Set()), () => {})

    expect(items.value[0]?.title).toBe("Create backup stopped when the server restarted")
    expect(items.value[0]?.tone).toBe("warning")
  })

  it("carries the handler's own sentence when there is one", () => {
    const jobs = ref([job("failed", { message: "pg_dump exited with code 1" })])
    const items = outstandingJobs(jobs, () => ({ label: "Create backup", lines: [] }), ref(new Set()), () => {})

    expect(items.value[0]?.detail).toBe("pg_dump exited with code 1")
    expect(items.value[0]?.tone).toBe("error")
  })

  it("drops the one that has been waved away, and keeps the row it was about", () => {
    const failed = job("failed")
    const jobs = ref([failed])
    const waved = ref(new Set<string>())
    const items = outstandingJobs(jobs, () => ({ label: "Create backup", lines: [] }), waved, (id) => {
      waved.value = new Set([...waved.value, id])
    })

    items.value[0]?.dismiss?.()

    expect(items.value).toEqual([])
    expect(jobs.value).toEqual([failed])
  })
})

describe("the order things are shown in", () => {
  it("puts what is broken above what is merely waiting, and the newest first within each", () => {
    const sorted = ranked([item("info", 3), item("error", 1), item("warning", 2), item("error", 5)])

    expect(sorted.map((entry) => entry.id)).toEqual(["error5", "error1", "warning2", "info3"])
  })
})
