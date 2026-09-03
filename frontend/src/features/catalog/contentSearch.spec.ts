import { describe, expect, it } from "vitest"

import { ASK_KEY, rememberAnswer, shouldAsk } from "./contentSearch"

/** A storage that can be told to fail, which private windows do. */
function storage(initial: Record<string, string> = {}, broken = false) {
  const held = new Map(Object.entries(initial))
  return {
    held,
    getItem: (key: string) => {
      if (broken) throw new Error("storage is not available")
      return held.get(key) ?? null
    },
    setItem: (key: string, value: string) => {
      if (broken) throw new Error("storage is not available")
      held.set(key, value)
    },
    removeItem: (key: string) => {
      if (broken) throw new Error("storage is not available")
      held.delete(key)
    },
  }
}

describe("whether to warn before reading every file", () => {
  it("asks the first time, when nothing has been remembered", () => {
    expect(shouldAsk(storage())).toBe(true)
  })

  it("stops asking once told to", () => {
    const store = storage()

    rememberAnswer(store, false)

    expect(store.held.get(ASK_KEY)).toBe("never")
    expect(shouldAsk(store)).toBe(false)
  })

  it("asks again once the answer is taken back", () => {
    const store = storage({ [ASK_KEY]: "never" })

    rememberAnswer(store, true)

    expect(store.held.has(ASK_KEY)).toBe(false)
    expect(shouldAsk(store)).toBe(true)
  })

  it("treats anything else in the slot as no answer at all", () => {
    expect(shouldAsk(storage({ [ASK_KEY]: "yes" }))).toBe(true)
  })

  it("asks when the storage cannot be read, which is the safe half", () => {
    expect(shouldAsk(storage({}, true))).toBe(true)
  })

  it("does not throw when the storage cannot be written to", () => {
    expect(() => {
      rememberAnswer(storage({}, true), false)
    }).not.toThrow()
  })
})
