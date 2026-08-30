import { describe, expect, it } from "vitest"

import { ACCESS_LABELS, atLeast, GRANT_OPTIONS } from "./access"
import type { Access } from "./access"

const SCALE: Access[] = ["read", "write", "structure", "own"]

describe("atLeast", () => {
  it("admits everything below the level held", () => {
    for (const [index, held] of SCALE.entries()) {
      for (const [needed, required] of SCALE.entries()) {
        expect(atLeast(held, required)).toBe(index >= needed)
      }
    }
  })
})

describe("the vocabulary", () => {
  it("has a wording for every level", () => {
    for (const level of SCALE) {
      expect(ACCESS_LABELS[level]).toBeTruthy()
    }
  })

  it("does not offer ownership as something to give away", () => {
    // The server refuses it too; this is the same statement made where the
    // choice is drawn, so the refusal never has to be seen.
    expect(GRANT_OPTIONS.map((option) => option.value)).toEqual([
      "read",
      "write",
      "structure",
    ])
  })
})
