import { describe, expect, it } from "vitest"

import {
  ageLabel,
  freshnessLabel,
  freshnessOf,
  freshnessTooltip,
  isLive,
  LIVE_WINDOW_MS,
  windowLabel,
} from "./freshness"

const NOW = 1_700_000_000_000

describe("what a reply says about itself", () => {
  it("reads the outcome and counts the age back from now", () => {
    const freshness = freshnessOf(
      { "x-data-cache": "hit", "x-data-cache-age": "42.000" },
      NOW
    )

    expect(freshness.outcome).toBe("hit")
    expect(freshness.readAt).toBe(NOW - 42_000)
  })

  it("treats a reply without the headers as a read of the source", () => {
    // A route that does not cache sends nothing, and the server's own word
    // for a source with no freshness rules is bypass.
    const freshness = freshnessOf(undefined, NOW)

    expect(freshness.outcome).toBe("bypass")
    expect(freshness.readAt).toBe(NOW)
  })

  it("refuses an outcome it does not know and a negative age", () => {
    const freshness = freshnessOf(
      { "x-data-cache": "borrowed", "x-data-cache-age": "-9" },
      NOW
    )

    expect(freshness.outcome).toBe("bypass")
    expect(freshness.readAt).toBe(NOW)
  })
})

describe("whether what is on screen is live", () => {
  it("is live only while the reply is the read and nothing has aged", () => {
    const read = freshnessOf({ "x-data-cache": "miss" }, NOW)

    expect(isLive(read, NOW)).toBe(true)
    // The same page, four minutes later. Nothing about it changed except
    // that it is not what the source holds now, which is the whole point.
    expect(isLive(read, NOW + 240_000)).toBe(false)
    expect(freshnessLabel(read, NOW)).toBe("Live")
    expect(freshnessLabel(read, NOW + 240_000)).toBe("4m")
  })

  it("stays live long enough to be seen", () => {
    // The reload wears this and swaps its icon on the turn (D112). A window
    // of one second meant the swap happened before anybody had looked up.
    const read = freshnessOf({ "x-data-cache": "miss" }, NOW)

    expect(LIVE_WINDOW_MS).toBeGreaterThanOrEqual(3000)
    expect(isLive(read, NOW + LIVE_WINDOW_MS - 1)).toBe(true)
    expect(isLive(read, NOW + LIVE_WINDOW_MS)).toBe(false)
  })

  it("is never live when the server said it kept the answer", () => {
    const kept = freshnessOf(
      { "x-data-cache": "hit", "x-data-cache-age": "3" },
      NOW
    )

    expect(isLive(kept, NOW)).toBe(false)
    expect(freshnessLabel(kept, NOW)).toBe("3s")
  })
})

describe("how long ago, in words", () => {
  it("climbs from seconds to days", () => {
    expect(ageLabel(4_000)).toBe("4s")
    expect(ageLabel(90_000)).toBe("2m")
    expect(ageLabel(3_600_000)).toBe("1h")
    expect(ageLabel(172_800_000)).toBe("2d")
  })

  it("says what a window is, and that nothing is one too", () => {
    expect(windowLabel(0)).toBe("nothing")
    expect(windowLabel(30)).toBe("30s")
    expect(windowLabel(300)).toBe("5m")
  })
})

describe("the sentence for somebody who stopped to ask", () => {
  it("names the age and what this connection was told to keep", () => {
    const kept = freshnessOf(
      { "x-data-cache": "hit", "x-data-cache-age": "90" },
      NOW
    )

    expect(freshnessTooltip(kept, 300, NOW)).toBe(
      "Read from the source 2m ago. This connection keeps answers for 5m."
    )
  })

  it("does not state a window its owner left to the source", () => {
    const read = freshnessOf({ "x-data-cache": "miss" }, NOW)

    expect(freshnessTooltip(read, null, NOW)).toBe(
      "Read from the source just now. This connection keeps answers for as " +
        "long as the source says."
    )
  })

  it("says plainly when nothing is kept at all", () => {
    const read = freshnessOf({ "x-data-cache": "bypass" }, NOW)

    expect(freshnessTooltip(read, 0, NOW)).toContain(
      "keeps nothing: every read reaches the source"
    )
  })
})
