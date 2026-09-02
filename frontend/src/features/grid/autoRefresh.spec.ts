import { beforeEach, describe, expect, it } from "vitest"

import {
  loadRefreshSeconds,
  refreshHeldBy,
  refreshItemName,
  refreshLabel,
  refreshSecondsOf,
  refreshTooltip,
  saveRefreshSeconds,
  REFRESH_SECONDS,
} from "./autoRefresh"

const CLEAR = { fetching: false, editing: false, inserting: false, away: false }

beforeEach(() => {
  localStorage.clear()
})

describe("how an interval is written", () => {
  it("says seconds under a minute and minutes above one", () => {
    expect(refreshLabel(5)).toBe("5 s")
    expect(refreshLabel(30)).toBe("30 s")
    expect(refreshLabel(60)).toBe("1 min")
    expect(refreshLabel(300)).toBe("5 min")
  })

  it("names every offered interval back to itself", () => {
    for (const seconds of REFRESH_SECONDS) {
      expect(refreshSecondsOf(refreshItemName(seconds))).toBe(seconds)
    }
    expect(refreshSecondsOf(refreshItemName(null))).toBeNull()
  })

  it("does not resolve a name it never offered", () => {
    expect(refreshSecondsOf("s7")).toBeUndefined()
    expect(refreshSecondsOf("")).toBeUndefined()
  })
})

describe("what stops a tick", () => {
  it("lets one through when nothing is in the way", () => {
    expect(refreshHeldBy(CLEAR)).toBeNull()
  })

  it("holds while a cell is being edited", () => {
    expect(refreshHeldBy({ ...CLEAR, editing: true })).toBe(
      "while a cell is being edited"
    )
  })

  it("holds while a row is being written", () => {
    expect(refreshHeldBy({ ...CLEAR, inserting: true })).toBe(
      "while a row is being written"
    )
  })

  it("holds while the tab is not on screen", () => {
    expect(refreshHeldBy({ ...CLEAR, away: true })).toBe(
      "while this tab is not on screen"
    )
  })

  it("holds while the last read is still running", () => {
    expect(refreshHeldBy({ ...CLEAR, fetching: true })).toBe(
      "while the last read is still running"
    )
  })

  it("names what the user is doing before what the grid is doing", () => {
    // A read is always under way while a cell is saved; saying so instead of
    // "a cell is being edited" would explain the wrong thing.
    expect(refreshHeldBy({ ...CLEAR, editing: true, fetching: true })).toBe(
      "while a cell is being edited"
    )
  })
})

describe("what the button says", () => {
  it("offers the choice when it is off", () => {
    expect(refreshTooltip(null, null)).toBe("Refresh automatically")
  })

  it("states the interval when it is on", () => {
    expect(refreshTooltip(10, null)).toBe("Refreshing every 10 s")
  })

  it("states why nothing is happening when it is held", () => {
    expect(refreshTooltip(10, "while a cell is being edited")).toBe(
      "Refreshing every 10 s, paused while a cell is being edited"
    )
  })
})

describe("what a relation is remembered as refreshing at", () => {
  it("comes back for the relation it was stored against", () => {
    saveRefreshSeconds("c1", "public.orders", 5)

    expect(loadRefreshSeconds("c1", "public.orders")).toBe(5)
    expect(loadRefreshSeconds("c1", "public.items")).toBeNull()
    expect(loadRefreshSeconds("c2", "public.orders")).toBeNull()
  })

  it("forgets the relation when it is turned off", () => {
    saveRefreshSeconds("c1", "public.orders", 5)
    saveRefreshSeconds("c1", "public.orders", null)

    expect(loadRefreshSeconds("c1", "public.orders")).toBeNull()
    expect(
      localStorage.getItem(`dataplayer:grid:refresh:${JSON.stringify(["c1", "public.orders"])}`)
    ).toBeNull()
  })

  it("discards a stored value that is not an offered interval", () => {
    localStorage.setItem(
      `dataplayer:grid:refresh:${JSON.stringify(["c1", "public.orders"])}`,
      "7"
    )

    expect(loadRefreshSeconds("c1", "public.orders")).toBeNull()
  })

  it("discards a stored value that is not JSON at all", () => {
    localStorage.setItem(
      `dataplayer:grid:refresh:${JSON.stringify(["c1", "public.orders"])}`,
      "every 5 seconds"
    )

    expect(loadRefreshSeconds("c1", "public.orders")).toBeNull()
  })
})
