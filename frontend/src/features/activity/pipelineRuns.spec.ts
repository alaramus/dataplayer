import { describe, expect, it } from "vitest"

import type { JobPublic } from "@/client"
import { pipelineLines, pipelineRunOf, pipelineWriting } from "./pipelineRuns"
import { jobTitle, serverRow } from "./presentation"
import { transferChanges, transferWriting } from "./transfers"

function step(title: string, outcome: string, extra: Record<string, unknown> = {}) {
  return {
    link_id: `link-${title}`, title,
    source_connection: "Sales", destination_connection: "Files",
    source_label: "Sales · orders", target_label: "Files · reports",
    destination_connector_id: "files", changes_source: false,
    paste: { source_connector_id: "sales", source_node_ids: ["orders"], mode: "copy", kind: "relation_csv" },
    outcome, message: null, transfer: null, started_at: null, finished_at: null,
    ...extra,
  }
}

function job(changes: Partial<JobPublic> = {}, steps: unknown[] = []): JobPublic {
  return {
    id: "run-1", kind: "pipeline.run", subject_id: "pipeline-1",
    parameters: {
      version: 1, pipeline_id: "pipeline-1", pipeline_name: "Nightly",
      steps: steps.length > 0 ? steps : [
        step("Save as CSV", "done", { message: "orders.csv saved in reports" }),
        step("Create a table", "running"),
        step("Add rows", "waiting"),
      ],
    },
    state: "running", step: "running its links", step_index: 1, step_count: 2,
    message: null, created_at: "2026-09-26T10:00:00Z", started_at: null, finished_at: null,
    ...changes,
  }
}

describe("a pipeline's run as its job records it", () => {
  it("is read step by step, and anything unrecognised is an ordinary job", () => {
    expect(pipelineRunOf(job())?.steps.map((one) => one.outcome)).toEqual(["done", "running", "waiting"])
    expect(pipelineRunOf(job({}, [{ title: "half a step" }]))).toBeNull()
    expect(pipelineRunOf({ kind: "paste.transfer", parameters: job().parameters })).toBeNull()
    expect(jobTitle(job())).toBe("Pipeline Nightly")
  })

  it("says in the footer where it is, by the pipeline's name, and Stop ends it", () => {
    expect(serverRow(job(), undefined)).toMatchObject({
      label: "Pipeline · Nightly",
      brief: "Nightly · 2 of 3: Create a table",
      progress: 1 / 3,
      measurement: "1 of 3 links",
      canStop: true,
      controlsHint: "Stops the link running now; the links after it are not run.",
    })
    expect(pipelineLines(job(), pipelineRunOf(job())!)).toEqual([
      "2 of 3: Create a table — Sales · orders → Files · reports",
    ])
    const waiting = job({ step: "waiting for a free transfer slot" })
    expect(pipelineLines(waiting, pipelineRunOf(waiting)!).at(-1)).toBe("Waiting for a free transfer slot")
  })

  it("lists each link under the run's sentence once it has ended", () => {
    const ended = job(
      { state: "failed", message: "Stopped at 2 of 3, Create a table: no columns; 1 not run" },
      [
        step("Save as CSV", "done", { message: "orders.csv saved in reports" }),
        step("Create a table", "failed", { message: "no columns" }),
        step("Add rows", "not_run"),
      ]
    )
    expect(pipelineLines(ended, pipelineRunOf(ended)!)).toEqual([
      "Stopped at 2 of 3, Create a table: no columns; 1 not run",
      "1. Save as CSV — orders.csv saved in reports",
      "2. Create a table — no columns",
      "3. Add rows — not run",
    ])
    // The server stopped under it: nothing settled the link in hand.
    const cut = job({ state: "interrupted", message: "The server stopped while this was running" })
    expect(pipelineLines(cut, pipelineRunOf(cut)!).slice(2)).toEqual([
      "2. Create a table — interrupted",
      "3. Add rows — not run",
    ])
  })

  it("re-reads the connections its links wrote into as they end", () => {
    const writing = (one: JobPublic) => transferWriting(one) ?? pipelineWriting(one)
    const first = transferChanges(new Map(), [job()], new Set(), writing)
    expect(first.touched).toEqual([])
    const later = job({}, [
      step("Save as CSV", "done"),
      step("Create a table", "done"),
      step("Add rows", "running", { destination_connector_id: "warehouse", changes_source: true }),
    ])
    expect(transferChanges(first.seen, [later], new Set(), writing).touched).toEqual([
      { connectorId: "files", settled: false },
      { connectorId: "warehouse", settled: false },
      { connectorId: "sales", settled: false },
    ])
    const done = job({ state: "succeeded", message: "All 3 links ran" }, [
      step("Save as CSV", "done"), step("Create a table", "done"), step("Add rows", "done"),
    ])
    expect(transferChanges(new Map(), [done], new Set(["run-1"]), writing).ended.map((one) => one.id)).toEqual(["run-1"])
  })
})
