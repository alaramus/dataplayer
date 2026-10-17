import { afterEach, describe, expect, it, vi } from "vitest"

import { newId } from "./ids"

describe("newId", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("is a version 4 UUID", () => {
    expect(newId()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })

  it("differs from one call to the next", () => {
    const ids = new Set(Array.from({ length: 100 }, () => newId()))
    expect(ids.size).toBe(100)
  })

  it("works where the page is not a secure context", () => {
    vi.stubGlobal("crypto", { getRandomValues: crypto.getRandomValues.bind(crypto) })
    expect(newId()).toMatch(/^[0-9a-f-]{36}$/)
  })
})
