import { describe, expect, it } from "vitest"

import type { StoreUsage } from "@/client"
import { originWording, removalWarning, sizeWording, tierWording } from "./storeFacts"

const usage: StoreUsage = {
  origin: "started",
  address: "dataplayer-svc-timescaledb-f207:5432/dataplayer",
  bytes: 3 * 1024 * 1024,
  series: 457,
  tiers: [
    { name: "raw", width_seconds: 0, kept_seconds: 7 * 86400 },
    { name: "5m", width_seconds: 300, kept_seconds: 35 * 86400 },
    { name: "1h", width_seconds: 3600, kept_seconds: 400 * 86400 },
  ],
}

describe("what the store window says", () => {
  it("says how long each table keeps what", () => {
    expect(usage.tiers.map(tierWording)).toEqual([
      "Samples as they came: kept 7 d",
      "Averages over 5 min: kept 35 d",
      "Averages over 1 h: kept 400 d",
    ])
  })

  it("measures the store, or says it could not", () => {
    expect(sizeWording(usage)).toBe("3 MB on disk, 457 series")
    expect(sizeWording({ ...usage, bytes: null, series: null })).toBe("Not answering, so not measured")
  })

  it("tells a started store from a connected one", () => {
    expect(originWording(usage)).toContain("started on this server")
    expect(originWording({ ...usage, origin: "connected" })).toContain("An existing TimescaleDB")
  })

  it("warns that everybody's samples go, and that a connected database stays", () => {
    expect(removalWarning(usage)).toContain("every sample of every person")
    expect(removalWarning(usage)).not.toContain("The database itself stays")
    expect(removalWarning({ ...usage, origin: "connected" })).toContain("The database itself stays")
  })
})
