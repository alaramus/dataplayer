import { describe, expect, it } from "vitest"

import type { JobPublic } from "@/client"
import { createOperations } from "@/shared/operations"
import { foreground, localRow, serverRow } from "./presentation"

const job: JobPublic = {
  id: "job-one", kind: "service.create", subject_id: null, parameters: null,
  state: "running", step: "pulling the image", step_index: 2, step_count: 7,
  message: null, created_at: "2026-09-04T10:00:00Z", started_at: null, finished_at: null,
}

describe("process presentation", () => {
  it("never turns Docker steps into a percentage or offers a fictitious pause", () => {
    const row = serverRow(job, "Development PostgreSQL")
    expect(row.label).toContain("Development PostgreSQL")
    expect(row.detail).toContain("pulling the image (2 of 7)")
    expect(row).toMatchObject({ progress: null, canPause: false, canResume: false, canStop: true })
    expect(serverRow({ ...job, state: "cancelled" }, undefined)).toMatchObject({
      active: false, status: "Stopped", canStop: false,
    })
  })

  it("measures transfer separately from server completion", async () => {
    const registry = createOperations()
    const task = registry.start("Upload", 1)
    await task.next("data.csv")
    task.transfer(40, 100)
    expect(localRow(registry.items.value[0]!)).toMatchObject({ progress: 0.4, active: true })
    task.transfer(100, 100)
    expect(localRow(registry.items.value[0]!)).toMatchObject({ progress: null, active: true })
  })

  it("shows moving work ahead of a paused batch and keeps batch counts honest", async () => {
    const registry = createOperations()
    const task = registry.start("Delete", 4)
    await task.next("first")
    registry.pause(task.id)
    task.complete()
    const waiting = task.next("second")
    const paused = localRow(registry.items.value[0]!)
    const moving = serverRow(job, undefined)
    expect(paused).toMatchObject({ paused: true, progress: 0.25, canResume: true })
    expect(foreground([paused, moving])).toBe(moving)
    registry.stop(task.id)
    expect(await waiting).toBe(false)
  })

  it("counts a source operation's settled targets and names what needs a look", () => {
    const target = (name: string, outcome: string, message: string | null = null) => ({
      target: { schema_name: "_timescaledb_internal", name }, outcome, message, observed: null,
    })
    const record = { title: "Compress chunks", summary: 'Compress 3 chunks of "lab"."metrics" as a job' }
    const running: JobPublic = {
      ...job, kind: "source.operation", subject_id: "connector-one",
      step: "carrying out the reviewed plan", step_index: 2, step_count: 3,
      parameters: { ...record, targets: [target("a", "completed"), target("b", "running"), target("c", "pending")] },
    }
    const row = serverRow(running, "Lab")
    expect(row).toMatchObject({
      label: "Compress chunks · Lab", measurement: "1 of 3 processed", progress: 1 / 3, canStop: true,
    })
    expect(row.detail).toContain("Now: _timescaledb_internal.b")
    expect(row.controlsHint).toContain("stops before the next target")

    const failed = serverRow({
      ...running, state: "failed", message: "Compress 3 chunks: 1 done, 1 refused, 1 not attempted",
      parameters: {
        ...record,
        targets: [
          target("a", "completed"),
          target("b", "refused", "This chunk is in use; nothing was converted"),
          target("c", "pending"),
        ],
      },
    }, "Lab")
    expect(failed).toMatchObject({ measurement: "2 of 3 processed", progress: null, active: false })
    expect(failed.detail).toContain("1 done, 1 refused, 1 not attempted")
    expect(failed.detail).toContain("_timescaledb_internal.b: This chunk is in use; nothing was converted")
  })
})
