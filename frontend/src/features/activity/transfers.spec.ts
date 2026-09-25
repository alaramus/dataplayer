import { afterEach, describe, expect, it, vi } from "vitest"

import type { JobPublic } from "@/client"
import { serverRow } from "./presentation"
import {
  createRereader,
  REREAD_MS,
  transferBrief,
  transferChanges,
  transferLines,
  transferOf,
} from "./transfers"

const MB = 1024 * 1024

function item(name: string, outcome: string, extra: Record<string, unknown> = {}) {
  return {
    name, node_id: name, is_folder: false, size_bytes: 1, files: 1,
    arrived: outcome === "done" ? 1 : 0, failed: outcome === "failed" ? 1 : 0,
    skipped: 0, removed: 0, outcome, message: null, published_as: null, rows: null,
    ...extra,
  }
}

function job(changes: Partial<JobPublic> = {}, parameters: Record<string, unknown> = {}): JobPublic {
  return {
    id: "job-1", kind: "paste.transfer", subject_id: "ssh",
    parameters: {
      version: 2, kind: "file_copy", title: "Copy files", doing: "Copying", done: "copied",
      mode: "copy", conflict: "refuse",
      source_connector_id: "files", source_label: "Files",
      destination_connector_id: "ssh", destination_node_id: null, destination_label: "SSH server",
      place_label: "SSH server", name: null,
      items: [item("q1.csv", "done"), item("q2.csv", "done"), item("q3.csv", "running"),
        item("q4.csv", "pending"), item("q5.csv", "pending")],
      bytes_total: 120 * MB, bytes_done: 45 * MB, files_done: 2, current: "q3.csv",
      published: 2, problems: [], problems_more: 0,
      ...parameters,
    },
    state: "running", step: "transferring", step_index: 3, step_count: 4,
    message: null, created_at: "2026-09-25T10:00:00Z", started_at: null, finished_at: null,
    ...changes,
  }
}

afterEach(() => {
  vi.useRealTimers()
})

describe("a transfer as its job records it", () => {
  it("is read field by field, and anything unrecognised is an ordinary job", () => {
    expect(transferOf(job())?.items).toHaveLength(5)
    expect(transferOf(job({}, { items: [item("q1.csv", "vanished")] }))).toBeNull()
    expect(transferOf(job({}, { doing: undefined }))).toBeNull()
    expect(transferOf(job({}, { problems: [{ path: "a" }] }))).toBeNull()
    expect(transferOf(job({ kind: "service.create" }))).toBeNull()
  })

  it("names what it does and where in the footer, with measured bytes", () => {
    const transfer = transferOf(job())
    expect(transfer && transferBrief(transfer)).toBe("Copying to SSH server · 45.0 MB of 120.0 MB")
    const table = transferOf(job({}, {
      doing: "Saving as CSV", bytes_total: null, bytes_done: 12 * MB,
      items: [item("orders", "running", { rows: 1200 })], current: "orders",
    }))
    expect(table && transferBrief(table)).toBe("Saving as CSV to SSH server · 12.0 MB written")
  })

  it("shows the file in hand by its path and how far, then each outcome", () => {
    const running = job()
    expect(transferLines(running, transferOf(running)!)).toEqual(["q3.csv — 3 of 5"])
    const deep = job({}, {
      items: [item("reports", "running", { is_folder: true, files: 4211 })],
      current: "reports/2025/q3.csv", files_done: 311,
    })
    expect(transferLines(deep, transferOf(deep)!)).toEqual(["reports/2025/q3.csv — 312 of 4,211"])
    const waiting = job({ step: "waiting for a free transfer slot" })
    expect(transferLines(waiting, transferOf(waiting)!)).toEqual(["Waiting for a free transfer slot"])
    const removing = job({ step: "removing the sources" })
    expect(transferLines(removing, transferOf(removing)!)).toEqual(["Removing the sources"])

    const ended = job({ state: "failed", message: "Copied 2 of 5 files to SSH server; 1 failed, 2 not attempted" }, {
      items: [
        item("q1.csv", "done"),
        item("q2.csv", "done", { published_as: "q2 (1).csv" }),
        item("q3.csv", "failed", { message: "q3.csv changed while it was being copied" }),
        item("q4.csv", "pending"),
        item("q5.csv", "running"),
      ],
    })
    expect(transferLines(ended, transferOf(ended)!)).toEqual([
      "Copied 2 of 5 files to SSH server; 1 failed, 2 not attempted",
      "q1.csv — copied",
      "q2.csv — copied as q2 (1).csv",
      "q3.csv changed while it was being copied",
      "q4.csv — not attempted",
      "q5.csv — interrupted",
    ])
  })

  it("counts a ticked folder, then lists the files that did not arrive", () => {
    const ended = job({ state: "failed", message: "Copied 4,208 of 4,211 files to SSH server; 3 failed" }, {
      items: [item("reports", "failed", {
        is_folder: true, files: 4211, arrived: 4208, failed: 3, skipped: 1, published_as: "reports (1)",
      })],
      problems: [
        { path: "reports/a.csv", message: "reports/a.csv could not be copied" },
        { path: "reports/link", message: "reports/link is a link and was skipped" },
      ],
    })
    expect(transferLines(ended, transferOf(ended)!)).toEqual([
      "Copied 4,208 of 4,211 files to SSH server; 3 failed",
      "reports as reports (1) — 4,208 copied, 3 failed, 1 skipped",
      "reports/a.csv could not be copied",
      "reports/link is a link and was skipped",
    ])
    const moved = job({ state: "failed", message: null }, {
      mode: "move", done: "moved",
      items: [item("tree", "kept", { is_folder: true, files: 3, arrived: 3, removed: 2 })],
    })
    expect(transferLines(moved, transferOf(moved)!)).toEqual(["tree — 2 moved, 1 kept at the source"])
  })

  it("lists the first ten of each and counts the rest", () => {
    const many = Array.from({ length: 12 }, (_, index) => item(`f${String(index)}.txt`, "done"))
    const problems = Array.from({ length: 11 }, (_, index) => ({ path: `p${String(index)}`, message: `p${String(index)} failed` }))
    const ended = job({ state: "failed", message: "Copied" }, { items: many, problems, problems_more: 89 })
    const lines = transferLines(ended, transferOf(ended)!)
    expect(lines).toHaveLength(1 + 11 + 11)
    expect(lines[11]).toBe("and 2 more")
    expect(lines.at(-1)).toBe("and 90 more")
  })

  it("is a Processes row with both connections, a bar only when a total is known, and Stop", () => {
    expect(serverRow(job(), undefined)).toMatchObject({
      label: "Copy files · Files → SSH server",
      brief: "Copying to SSH server · 45.0 MB of 120.0 MB",
      progress: 45 / 120,
      canStop: true,
      controlsHint: "Stops at once; what already arrived stays.",
    })
    expect(serverRow(job({}, { bytes_total: null }), undefined).progress).toBeNull()
    expect(serverRow(job({}, { mode: "move" }), undefined).controlsHint)
      .toBe("Stops at once; the sources stay until everything has arrived.")
  })
})

describe("following a transfer", () => {
  it("re-reads the destination as files arrive, and a move's source too", () => {
    const first = transferChanges(new Map(), [job()], new Set())
    expect(first.touched).toEqual([])

    const later = job({}, { published: 3 })
    const second = transferChanges(first.seen, [later], new Set())
    expect(second.touched).toEqual([{ connectorId: "ssh", settled: false }])

    const moving = job({ state: "succeeded" }, { mode: "move", published: 3 })
    expect(transferChanges(second.seen, [moving], new Set()).touched).toEqual([
      { connectorId: "ssh", settled: true },
      { connectorId: "files", settled: true },
    ])
  })

  it("tells the tab that started it how it ended, even before it was ever listed", () => {
    const done = job({ state: "succeeded", message: "Copied 5 files to SSH server" }, { published: 5 })

    const told = transferChanges(new Map(), [done], new Set(["job-1"]))

    expect(told.touched).toEqual([{ connectorId: "ssh", settled: true }])
    expect(told.ended.map((ended) => ended.id)).toEqual(["job-1"])
    // Another tab re-reads nothing it never saw run, and tells nothing.
    expect(transferChanges(new Map(), [done], new Set())).toMatchObject({ touched: [], ended: [] })
  })

  it("re-reads at most every two seconds while it runs, and at once when it ends", () => {
    vi.useFakeTimers()
    const announced: string[] = []
    const rereader = createRereader((connectorId) => { announced.push(connectorId) })

    rereader.reread("ssh", false)
    rereader.reread("ssh", false)
    rereader.reread("ssh", false)
    expect(announced).toEqual(["ssh"])
    vi.advanceTimersByTime(REREAD_MS)
    // The arrival in between is not dropped: it is read once, late.
    expect(announced).toEqual(["ssh", "ssh"])

    rereader.reread("ssh", false)
    rereader.reread("ssh", true)
    expect(announced).toEqual(["ssh", "ssh", "ssh"])
    vi.advanceTimersByTime(REREAD_MS)
    expect(announced).toHaveLength(3)
    rereader.dispose()
  })
})
