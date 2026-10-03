import { describe, expect, it } from "vitest"

import {
  clockOf,
  followOf,
  MAX_ONLY,
  nothingFoundSentence,
  saidOf,
  secondsOf,
  stillSearching,
  typingNote,
} from "./outcomes"
import { CONNECTIONS, GUIDE, IN_PG, outcome, plannedCell } from "./testing"

const IN_CONNECTION = plannedCell("connection:c1/names", IN_PG)
const ROWS = plannedCell("connections/names", CONNECTIONS)

describe("what an outcome says (D201)", () => {
  it("says a late cell's deadline and offers to try again", () => {
    expect(saidOf(outcome({ status: "late", deadline_seconds: 2 }), IN_CONNECTION)).toEqual({
      sentence: "Didn't answer in 2 s",
      gesture: { kind: "retry", label: "Try again" },
    })
  })

  it("says since when a connection cannot be reached and offers to search it anyway", () => {
    const since = new Date(2026, 9, 2, 14, 2).toISOString()
    expect(saidOf(outcome({ status: "skipped", reason: "unreachable", since }), IN_CONNECTION)).toEqual({
      sentence: "Can't be reached since 14:02",
      gesture: { kind: "anyway", label: "Search anyway" },
    })
  })

  it("sends a cell typing did not ask to Enter", () => {
    expect(saidOf(outcome({ status: "skipped", reason: "not_in_context" }), IN_CONNECTION)).toEqual({
      sentence: "Not searched while typing",
      gesture: { kind: "enter", label: "Press Enter" },
    })
  })

  it("says where a cell stopped and offers that connection alone", () => {
    expect(
      saidOf(outcome({ status: "stopped", notice: "Stopped after 100 matches" }), IN_CONNECTION)
    ).toEqual({
      sentence: "Stopped after 100 matches",
      gesture: { kind: "alone", label: "Search only this connection" },
    })
  })

  it("offers no connection alone for a cell that is not one", () => {
    expect(saidOf(outcome({ status: "stopped", notice: "Stopped" }), ROWS)?.gesture).toBeNull()
  })

  it("says a switched-off connection and one that cannot search, with nothing to do", () => {
    expect(saidOf(outcome({ status: "skipped", reason: "switched_off" }), IN_CONNECTION)).toEqual({
      sentence: "Switched off",
      gesture: null,
    })
    expect(saidOf(outcome({ status: "skipped", reason: "cannot_search" }), IN_CONNECTION)).toEqual({
      sentence: "Can't be searched by name",
      gesture: null,
    })
  })

  it("offers the cells left out by the ceiling of connections", () => {
    expect(saidOf(outcome({ status: "skipped", reason: "not_asked" }), IN_CONNECTION)).toEqual({
      sentence: "Not searched",
      gesture: { kind: "these", label: "Search these too" },
    })
  })

  it("offers the owner of a locked key to unlock it, and tells a grantee whose it is", () => {
    const locked = { status: "failed" as const, error_kind: "locked" as const }
    expect(saidOf(outcome({ ...locked, owned: true }), IN_CONNECTION)).toEqual({
      sentence: "Locked",
      gesture: { kind: "unlock", label: "Unlock the SSH key" },
    })
    expect(saidOf(outcome({ ...locked, owned: false }), IN_CONNECTION)).toEqual({
      sentence: "Locked by its owner",
      gesture: null,
    })
  })

  it("says a failure in the safe sentence it came with", () => {
    expect(
      saidOf(outcome({ status: "failed", error_kind: "unknown", message: "This could not be searched (ref 1a2b)" }), ROWS)
    ).toEqual({ sentence: "This could not be searched (ref 1a2b)", gesture: { kind: "retry", label: "Try again" } })
  })

  it("says nothing about a complete cell, but that there is more when there is", () => {
    expect(saidOf(outcome(), IN_CONNECTION)).toBeNull()
    expect(saidOf(outcome({ more: true }), IN_CONNECTION)).toEqual({
      sentence: "Found more than is shown",
      gesture: { kind: "more", label: "More in this connection" },
    })
  })

  it("counts the places when nothing was found", () => {
    expect(nothingFoundSentence(12)).toBe("Nothing found in all 12 places")
    expect(nothingFoundSentence(1)).toBe("Nothing found in the one place searched")
  })

  it("writes deadlines and times the way a person reads them", () => {
    expect(secondsOf(2)).toBe("2 s")
    expect(secondsOf(0.4)).toBe("0.4 s")
    expect(clockOf(new Date(2026, 0, 1, 9, 5).toISOString())).toBe("09:05")
    expect(stillSearching(1)).toBe("Still searching 1 place")
  })
})

describe("the one quiet line of the field", () => {
  it("counts what was late and what typing leaves to Enter", () => {
    expect(
      typingNote([
        { planned: IN_CONNECTION, outcome: outcome({ status: "late" }), hits: [] },
        { planned: ROWS, outcome: outcome({ status: "skipped", reason: "not_in_context" }), hits: [] },
        { planned: ROWS, outcome: outcome({ status: "skipped", reason: "too_costly" }), hits: [] },
        { planned: ROWS, outcome: outcome(), hits: [] },
      ])
    ).toBe("1 place didn't answer in time · 2 places not searched while typing · Press Enter to search everything")
  })

  it("is empty when everything was asked and answered", () => {
    expect(typingNote([{ planned: ROWS, outcome: outcome(), hits: [] }])).toBe("")
  })
})

describe("the ask a gesture makes", () => {
  it("asks a cell alone, on the lane of follow-ups", () => {
    expect(followOf({ kind: "alone", label: "Search only this connection" }, "orders", IN_CONNECTION, [])).toEqual({
      words: "orders",
      mode: "search",
      lane: "follow",
      only: [IN_CONNECTION.cell.place],
    })
  })

  it("asks a late cell again past the time it is held back for", () => {
    expect(followOf({ kind: "retry", label: "Try again" }, "orders", IN_CONNECTION, [])).toEqual({
      words: "orders",
      mode: "search",
      lane: "follow",
      only: [IN_CONNECTION.cell.place],
      insist: true,
    })
  })

  it("insists on a connection seen down", () => {
    expect(followOf({ kind: "anyway", label: "Search anyway" }, "orders", IN_CONNECTION, [])?.insist).toBe(true)
  })

  it("asks every cell not asked, at most as many as a request may name", () => {
    const cells = Array.from({ length: 10 }, (_, index) => ({
      planned: plannedCell(`connection:c${String(index)}/names`, { ...IN_PG, key: `connection:c${String(index)}` }),
      outcome: outcome({ status: "skipped", reason: "not_asked" }),
      hits: [],
    }))
    const asked = followOf({ kind: "these", label: "Search these too" }, "orders", IN_CONNECTION, [
      { planned: plannedCell("objects:guide/names", GUIDE), outcome: outcome(), hits: [] },
      ...cells,
    ])
    expect(asked?.only).toHaveLength(MAX_ONLY)
    expect(asked?.insist).toBe(true)
  })

  it("asks nothing for a gesture that goes somewhere instead", () => {
    expect(followOf({ kind: "enter", label: "Press Enter" }, "orders", IN_CONNECTION, [])).toBeNull()
    expect(followOf({ kind: "unlock", label: "Unlock the SSH key" }, "orders", IN_CONNECTION, [])).toBeNull()
  })
})
