import { describe, expect, it } from "vitest"

import type { KeepState, Outcome, PlannedCell } from "@/client"

import { isBusy, offersKeeping, statusLine, windowName } from "./state"

const NOW = Date.parse("2026-10-11T12:00:00Z")

function state(changed: Partial<KeepState>): KeepState {
  return {
    connector_id: "c1",
    name: "warehouse",
    adapter_type: "postgres",
    may_change: true,
    available: true,
    status: "kept",
    names: 1234,
    kept_at: "2026-10-11T11:48:00Z",
    ...changed,
  }
}

function planned(changed: Partial<PlannedCell> = {}): PlannedCell {
  return {
    key: "connection:c1/names",
    cell: { place: { kind: "connection", connector_id: "c1", node_id: null }, field: "names" },
    group: { key: "connection:c1", title: "warehouse", rank: 1000 },
    cost: "costly",
    way: "live",
    connector_id: "c1",
    ...changed,
  } as PlannedCell
}

function outcome(changed: Partial<Outcome>): Outcome {
  return { way: "live", status: "late", ...changed } as Outcome
}

const MINE = { owned: true, adapterType: "postgres" }

describe("statusLine", () => {
  it("says how many names and how old they are", () => {
    expect(statusLine(state({}), NOW)).toBe("1,234 names, read 12m ago")
  })

  it("says a renamed list will be read again", () => {
    expect(statusLine(state({ stale: true }), NOW)).toBe(
      "1,234 names, read 12m ago · changed since, reading again soon"
    )
  })

  it("adds why a list is partial", () => {
    expect(statusLine(state({ status: "partial", notice: "Time ran out" }), NOW)).toBe(
      "1,234 names, read 12m ago · Time ran out"
    )
  })

  it("keeps saying what is still used after a failed reading", () => {
    expect(statusLine(state({ status: "failed", notice: "No answer" }), NOW)).toBe(
      "Last reading failed: No answer. Still using 1,234 names, read 12m ago"
    )
    expect(statusLine(state({ status: "failed", notice: "No answer", kept_at: null }), NOW)).toBe(
      "Reading failed: No answer"
    )
  })

  it("says one name rather than one names", () => {
    expect(statusLine(state({ names: 1 }), NOW)).toBe("1 name, read 12m ago")
  })

  it("waits, reads and is off in words", () => {
    expect(statusLine(state({ status: "waiting", kept_at: null }), NOW)).toBe(
      "Waiting for its first reading"
    )
    expect(statusLine(state({ status: "reading", kept_at: null }), NOW)).toBe("Reading names…")
    expect(statusLine(state({ status: "off" }), NOW)).toBe("Not kept")
  })
})

describe("isBusy", () => {
  it("is busy while something is about to change", () => {
    expect(isBusy(state({}))).toBe(false)
    expect(isBusy(state({ status: "reading" }))).toBe(true)
    expect(isBusy(state({ refresh_asked: true }))).toBe(true)
    expect(isBusy(state({ stale: true }))).toBe(true)
  })
})

describe("windowName", () => {
  it("names each window and falls back to a day", () => {
    expect(windowName(3600)).toBe("1 hour")
    expect(windowName(604800)).toBe("1 week")
    expect(windowName(undefined)).toBe("1 day")
  })
})

describe("offersKeeping", () => {
  const types = ["postgres", "file"]

  it("offers it on one's own slow connection that keeps nothing yet", () => {
    expect(offersKeeping(planned(), outcome({}), MINE, types, new Set())).toBe(true)
    expect(
      offersKeeping(planned(), outcome({ status: "stopped" }), MINE, types, new Set())
    ).toBe(true)
  })

  it("does not offer it where it would not help or is not theirs", () => {
    const cell = planned()
    expect(offersKeeping(cell, outcome({ status: "complete" }), MINE, types, new Set())).toBe(false)
    expect(offersKeeping(cell, outcome({ way: "kept" }), MINE, types, new Set())).toBe(false)
    expect(offersKeeping(cell, outcome({}), { ...MINE, owned: false }, types, new Set())).toBe(false)
    expect(offersKeeping(cell, outcome({}), { ...MINE, adapterType: "s3" }, types, new Set())).toBe(false)
    expect(offersKeeping(cell, outcome({}), MINE, types, new Set(["c1"]))).toBe(false)
    expect(offersKeeping(cell, null, MINE, types, new Set())).toBe(false)
    expect(
      offersKeeping(
        planned({ cell: { place: { kind: "connection", connector_id: "c1", node_id: null }, field: "columns" } }),
        outcome({}),
        MINE,
        types,
        new Set()
      )
    ).toBe(false)
  })
})
