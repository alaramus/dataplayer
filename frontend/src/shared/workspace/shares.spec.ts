import { describe, expect, it } from "vitest"

import { sharesOf } from "./shares"

const sharesIn = (sizes: number[], hidden: boolean[]) =>
  sharesOf(sizes, hidden).map((one) => one.share)
const gapsIn = (sizes: number[], hidden: boolean[]) => sharesOf(sizes, hidden).map((one) => one.gaps)

describe("the share each section of a split takes", () => {
  it("is the size it was given when every section is on screen", () => {
    expect(sharesIn([20, 28, 52], [false, false, false])).toEqual([20, 28, 52])
  })

  it("leaves a hidden section's room to the sections after it", () => {
    // Forward and not over the whole row: the narrow column of connections
    // stays the width the user made it when the catalog goes. See P4.
    expect(sharesIn([20, 28, 52], [false, true, false])).toEqual([20, 0, 80])
  })

  it("shares that room out between them in proportion", () => {
    // Two cards of work, 30 and 20 of the row, take 24 and 16 of the 40 freed.
    // Given whole to the first of them, that card could then never be dragged
    // below 40 again.
    expect(sharesIn([10, 40, 30, 20], [false, true, false, false])).toEqual([10, 0, 54, 36])
  })

  it("leaves it to the section before when there is none after", () => {
    expect(sharesIn([20, 28, 52], [false, false, true])).toEqual([20, 80, 0])
  })

  it("carries several hidden sections in a row to the same place", () => {
    expect(sharesIn([20, 28, 52], [true, true, false])).toEqual([0, 0, 100])
  })

  it("leaves nothing to anybody when nothing is on screen", () => {
    expect(sharesIn([20, 80], [true, true])).toEqual([0, 0])
  })

  it("does not touch the sizes it was given", () => {
    // The tree keeps the width the user chose: hiding a column is how it looks
    // now, not what it was made. Bringing the panel back brings the width back.
    const sizes = [20, 28, 52]
    sharesOf(sizes, [false, true, false])
    expect(sizes).toEqual([20, 28, 52])
  })
})

describe("the sections a section stands in for", () => {
  it("are none while every section is on screen", () => {
    expect(gapsIn([20, 28, 52], [false, false, false])).toEqual([0, 0, 0])
  })

  it("are the one off the screen, for the section that takes its room", () => {
    // Its border is not drawn either, and neither are its own two edges, so
    // the row has those pixels to spend elsewhere. Spent by the section that
    // took its room, the columns in front of it keep the width they had.
    expect(gapsIn([20, 28, 52], [false, true, false])).toEqual([0, 0, 1])
  })

  it("go whole to the first of them, unlike the room itself", () => {
    // Shared out like the room, this would move from one card to the other as
    // the border between them is dragged, and the border would run ahead of
    // the pointer by those few pixels.
    expect(gapsIn([10, 40, 30, 20], [false, true, false, false])).toEqual([0, 0, 1, 0])
  })

  it("go back to the section before when there is none after", () => {
    expect(gapsIn([20, 28, 52], [false, false, true])).toEqual([0, 1, 0])
  })

  it("are one for every section off the screen", () => {
    expect(gapsIn([20, 28, 52], [true, true, false])).toEqual([0, 0, 2])
  })
})
