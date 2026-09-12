import { describe, expect, it } from "vitest"

import type { JobPublic } from "@/client"
import {
  operationLines,
  settledCount,
  sourceDataKeys,
  sourceOperationOf,
  touchedSources,
} from "./sourceOperations"

function target(name: string, outcome: string, extra: Record<string, unknown> = {}) {
  return {
    target: { schema_name: "_timescaledb_internal", name }, outcome, message: null, observed: null,
    ...extra,
  }
}

function job(targets: unknown[], state: JobPublic["state"] = "running"): JobPublic {
  return {
    id: "job-one", kind: "source.operation", subject_id: "connector-one",
    parameters: {
      version: 1, action: "timescale_compress_chunks", title: "Compress chunks",
      summary: 'Compress 3 chunks of "lab"."metrics" as a job', targets,
    },
    state, step: "carrying out the reviewed plan", step_index: 2, step_count: 3, message: null,
    created_at: "2026-09-11T10:00:00Z", started_at: null, finished_at: null,
  }
}

const RUNNING = job([target("a", "completed"), target("b", "running"), target("c", "pending")])

describe("source operations in Activity", () => {
  it("reads the title, the summary and every target's outcome", () => {
    const operation = sourceOperationOf(RUNNING)
    expect(operation).toMatchObject({ title: "Compress chunks", summary: 'Compress 3 chunks of "lab"."metrics" as a job' })
    expect(operation?.targets.map((one) => [one.name, one.outcome])).toEqual([
      ["a", "completed"], ["b", "running"], ["c", "pending"],
    ])
    expect(operation === null ? -1 : settledCount(operation)).toBe(1)
  })

  it.each([
    ["another kind of job", { ...RUNNING, kind: "backup.create" }],
    ["no parameters", { ...RUNNING, parameters: null }],
    ["an outcome it does not know", job([target("a", "vanished")])],
    ["an observation it does not know", job([target("a", "completed", { observed: "elsewhere" })])],
    ["a target without a name", job([{ outcome: "pending", target: { schema_name: "x" } }])],
    ["no targets at all", job([])],
  ] as [string, JobPublic][])("draws %s as an ordinary job", (_, candidate) => {
    expect(sourceOperationOf(candidate)).toBeNull()
  })

  it("says what it is working on, then what somebody has to look at", () => {
    expect(operationLines(sourceOperationOf(RUNNING)!, true)).toEqual(["Now: _timescaledb_internal.b"])
    const finished = sourceOperationOf(job([
      target("a", "completed"),
      target("b", "refused", { message: "This chunk is in use; nothing was converted", observed: "unchanged" }),
      target("c", "unknown", { message: "The server stopped while this target was in progress; its outcome is unknown" }),
      target("d", "rolled_back", { observed: "gone" }),
    ], "failed"))!
    expect(operationLines(finished, false)).toEqual([
      "_timescaledb_internal.b: This chunk is in use; nothing was converted (now unchanged)",
      "_timescaledb_internal.c: The server stopped while this target was in progress; its outcome is unknown",
      "_timescaledb_internal.d: rolled_back (no longer there)",
    ])
  })

  it("re-reads a connection only when one of its operations moved", () => {
    const first = touchedSources(new Map(), [RUNNING])
    expect(first.connectorIds).toEqual([])
    expect(touchedSources(first.seen, [RUNNING]).connectorIds).toEqual([])
    const moved = job([target("a", "completed"), target("b", "completed"), target("c", "running")])
    expect(touchedSources(first.seen, [moved]).connectorIds).toEqual(["connector-one"])
    const ended = { ...RUNNING, state: "cancelled" as const }
    expect(touchedSources(first.seen, [ended]).connectorIds).toEqual(["connector-one"])
    const service: JobPublic = { ...RUNNING, id: "job-two", kind: "service.create", parameters: null }
    expect(touchedSources(new Map([["job-two", "running:0"]]), [service]).connectorIds).toEqual([])
  })

  it("re-reads everything the connection shows, its features included", () => {
    const keys = sourceDataKeys("connector-one")
    expect(keys).toContainEqual(["connectors", "connector-one", "features"])
    expect(keys).toContainEqual(["rows", "connector-one"])
    expect(keys).toContainEqual(["catalog", "connector-one"])
    expect(keys.every((key) => key.includes("connector-one"))).toBe(true)
  })
})
