import { describe, expect, it } from "vitest"

import { sharesOf } from "./shares"

describe("the share each section of a split takes", () => {
  it("is the size it was given when every section is on screen", () => {
    expect(sharesOf([20, 28, 52], [false, false, false])).toEqual([20, 28, 52])
  })

  it("leaves a hidden section's room to the rest, in proportion to what they have", () => {
    // The two that stay keep the ratio they had - 20 to 52 - and the 28 that
    // was freed is spread over them by it. Given whole to the one beside it,
    // that section could then never be dragged below 28 again. See P4.
    expect(sharesOf([20, 28, 52], [false, true, false])).toEqual([
      (20 * 100) / 72,
      0,
      (52 * 100) / 72,
    ])
  })

  it("adds up to the whole split whichever sections are hidden", () => {
    for (const hidden of [
      [false, false, true],
      [true, false, false],
      [true, true, false],
      [false, true, true],
    ]) {
      const total = sharesOf([20, 28, 52], hidden).reduce((sum, share) => sum + share, 0)
      expect(total).toBeCloseTo(100)
    }
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
