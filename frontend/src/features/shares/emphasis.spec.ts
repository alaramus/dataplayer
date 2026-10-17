import { describe, expect, it } from "vitest"

import { emphasized, strong } from "./emphasis"

describe("emphasized", () => {
  it("sets marked parameters apart from the sentence around them", () => {
    expect(emphasized(`${strong("orders")} is no longer in ${strong("prod")}.`)).toEqual([
      { text: "orders", strong: true },
      { text: " is no longer in ", strong: false },
      { text: "prod", strong: true },
      { text: ".", strong: false },
    ])
  })

  it("leaves a sentence without marks whole", () => {
    expect(emphasized("Nothing here")).toEqual([{ text: "Nothing here", strong: false }])
  })
})
