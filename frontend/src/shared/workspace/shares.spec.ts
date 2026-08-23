import { describe, expect, it } from "vitest"

import { sharesOf } from "./shares"

describe("the share each section of a split takes", () => {
  it("is the size it was given when every section is on screen", () => {
    expect(sharesOf([20, 28, 52], [false, false, false])).toEqual([20, 28, 52])
  })

  it("gives a hidden section's share whole to the next one along", () => {
    // Whole, and not spread over the rest: shared out proportionally, the
    // column of connections would swell from a fifth of the screen to more
    // than a quarter on the first run, which is not what was freed and not
    // what the room was freed for. See P4.
    expect(sharesOf([20, 28, 52], [false, true, false])).toEqual([20, 0, 80])
  })

  it("gives it to the one before when it is the last", () => {
    expect(sharesOf([20, 28, 52], [false, false, true])).toEqual([20, 80, 0])
  })

  it("carries the share of the first section on to the second", () => {
    expect(sharesOf([20, 28, 52], [true, false, false])).toEqual([0, 48, 52])
  })

  it("carries several hidden sections in a row to the same neighbour", () => {
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
