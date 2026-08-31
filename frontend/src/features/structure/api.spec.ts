import { describe, expect, it } from "vitest"

import { structureInvalidationKeys } from "./api"

describe("a successful relation structure change", () => {
  it("invalidates the model, rows and source-issued content", () => {
    expect(structureInvalidationKeys("c1", "public.orders")).toEqual([
      ["relationModel", "c1", "public.orders"],
      ["rows", "c1"],
      ["content", "c1"],
    ])
  })
})
