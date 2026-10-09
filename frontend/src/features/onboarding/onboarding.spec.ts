import { describe, expect, it } from "vitest"

import { ONBOARDING_STEPS } from "./onboarding"

describe("onboarding steps", () => {
  it("covers the six demo clips, each with a unique id and a video source", () => {
    expect(ONBOARDING_STEPS).toHaveLength(6)
    const ids = ONBOARDING_STEPS.map((step) => step.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const step of ONBOARDING_STEPS) {
      expect(step.title).not.toBe("")
      expect(step.src).toMatch(/^\/onboarding\/.+\.(webm|mp4)$/)
    }
  })
})
