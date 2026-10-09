import { beforeEach, describe, expect, it } from "vitest"

import {
  ONBOARDING_DONE_KEY,
  ONBOARDING_STEPS,
  isOnboardingDone,
  markOnboardingDone,
  shouldShowOnboarding,
} from "./onboarding"

function freshStorage(): Storage {
  const backing = new Map<string, string>()
  return {
    getItem: (key: string) => backing.get(key) ?? null,
    setItem: (key: string, value: string) => {
      backing.set(key, value)
    },
    removeItem: (key: string) => {
      backing.delete(key)
    },
    clear: () => {
      backing.clear()
    },
    key: (index: number) => [...backing.keys()][index] ?? null,
    get length() {
      return backing.size
    },
  } as Storage
}

describe("onboarding state", () => {
  let storage: Storage

  beforeEach(() => {
    storage = freshStorage()
  })

  it("shows the tour until it is finished or skipped", () => {
    expect(shouldShowOnboarding(storage)).toBe(true)

    markOnboardingDone(storage)
    expect(isOnboardingDone(storage)).toBe(true)
    expect(storage.getItem(ONBOARDING_DONE_KEY)).toBe("1")
    expect(shouldShowOnboarding(storage)).toBe(false)
  })

  it("survives blocked storage without throwing", () => {
    const blocked = {
      getItem: () => {
        throw new Error("denied")
      },
      setItem: () => {
        throw new Error("denied")
      },
    } as unknown as Storage
    expect(() => markOnboardingDone(blocked)).not.toThrow()
    expect(shouldShowOnboarding(blocked)).toBe(true)
  })
})

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
