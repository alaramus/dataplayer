import { describe, expect, it } from "vitest"

import { duration, formatValue } from "./seriesFormat"

describe("a value as it is read", () => {
  it("scales bytes and kilobytes to the nearest step", () => {
    expect(formatValue(512, "B")).toBe("512 B")
    expect(formatValue(1536, "B")).toBe("1.50 KB")
    // /proc/meminfo in kilobytes: 15917216 kB is about 15 GB.
    expect(formatValue(15917216, "kB")).toBe("15.2 GB")
  })

  it("scales a bit rate the way iftop does", () => {
    expect(formatValue(2048, "b/s")).toBe("2 Kb/s")
  })

  it("keeps one decimal of a percentage", () => {
    expect(formatValue(0.708629, "%")).toBe("0.7 %")
  })

  it("reads seconds as a duration", () => {
    expect(formatValue(45, "s")).toBe("45 s")
    expect(duration(3 * 3600 + 4 * 60)).toBe("3 h 4 min")
    expect(duration(21 * 86400 + 4 * 3600 + 59)).toBe("21 d 4 h")
    expect(duration(120)).toBe("2 min")
  })

  it("leaves a unitless value short and says an unknown unit", () => {
    expect(formatValue(0.094727, "")).toBe("0.09")
    expect(formatValue(12, "")).toBe("12")
    expect(formatValue(3.5, "rpm")).toBe("3.50 rpm")
  })
})

describe("a rate a connection reports", () => {
  it("reads a count per second and bytes per second", () => {
    expect(formatValue(2.5, "/s")).toBe("2.50/s")
    expect(formatValue(4096, "B/s")).toBe("4 KB/s")
    expect(formatValue(2048, "b/s")).toBe("2 Kb/s")
  })
})

