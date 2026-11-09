import { describe, expect, it } from "vitest"

import { storageWording } from "./storage"

describe("storageWording", () => {
  it("says how much of the limit is in use, and fills the bar to match", () => {
    const shown = storageWording({ used_bytes: 512 * 1024 * 1024, limit_bytes: 1024 * 1024 * 1024 })
    expect(shown.text).toContain("512")
    expect(shown.text).toContain("1")
    expect(shown.fraction).toBe(0.5)
  })

  it("draws no bar where there is no limit", () => {
    const shown = storageWording({ used_bytes: 10, limit_bytes: null })
    expect(shown.fraction).toBeNull()
    expect(shown.text).toContain("10")
  })
})
