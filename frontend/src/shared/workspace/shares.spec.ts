import { describe, expect, it } from "vitest"

import { sharesOf } from "./shares"

describe("the share each section of a split takes", () => {
  it("is the size it was given when every section is on screen", () => {
    expect(sharesOf([20, 28, 52], [false, false, false])).toEqual([20, 28, 52])
  })

  it("leaves a hidden section's room to the sections after it", () => {
    // Forward and not over the whole row: the narrow column of connections
    // stays the width the user made it when the catalog goes. See P4.
    expect(sharesOf([20, 28, 52], [false, true, false])).toEqual([20, 0, 80])
  })

  it("shares that room out between them in proportion", () => {
    // Two cards of work, 30 and 20 of the row, take 24 and 16 of the 40 freed.
    // Given whole to the first of them, that card could then never be dragged
    // below 40 again.
    expect(sharesOf([10, 40, 30, 20], [false, true, false, false])).toEqual([10, 0, 54, 36])
  })

  it("leaves it to the section before when there is none after", () => {
    expect(sharesOf([20, 28, 52], [false, false, true])).toEqual([20, 80, 0])
  })

  it("carries several hidden sections in a row to the same place", () => {
    expect(sharesOf([20, 28, 52], [true, true, false])).toEqual([0, 0, 100])
  })

  it("leaves nothing to anybody when nothing is on screen", () => {
    expect(sharesOf([20, 80], [true, true])).toEqual([0, 0])
  })

  it("does not touch the sizes it was given", () => {
    // The tree keeps the width the user chose: hiding a column is how it looks
    // now, not what it was made. Bringing the panel back brings the width back.
    const sizes = [20, 28, 52]
    sharesOf(sizes, [false, true, false])
    expect(sizes).toEqual([20, 28, 52])
  })
})
