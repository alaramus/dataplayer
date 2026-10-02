import { describe, expect, it } from "vitest"

import { sharesOf, tradeShares } from "./shares"

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

describe("a border dragged between two sections on the screen", () => {
  const drawn = (sizes: number[], hidden: boolean[]) => sharesIn(sizes, hidden)

  it("moves what one side loses to the other while every section is on screen", () => {
    const sizes = tradeShares([20, 28, 52], [false, false, false], 1, 2, 10, 5, 5)
    expect(sizes).not.toBeNull()
    expect(sizes?.[0]).toBeCloseTo(20)
    expect(sizes?.[1]).toBeCloseTo(38)
    expect(sizes?.[2]).toBeCloseTo(42)
  })

  it("lets the card after a column on the bar narrow past that column's room", () => {
    // The catalog beside the work card goes to the bar and the work card takes
    // its 40 whole. Traded in sizes the work card stopped at 40 more than its
    // minimum, and the catalog in front of it could not be widened.
    const hidden = [false, false, true, false]
    const sizes = tradeShares([15, 25, 40, 20], hidden, 1, 3, 50, 5, 5)
    expect(sizes).not.toBeNull()
    const shares = drawn(sizes ?? [], hidden)
    expect(shares[1]).toBeCloseTo(75)
    expect(shares[3]).toBeCloseTo(10)
  })

  it("brings the column on the bar back as the same part of the room it left", () => {
    // It took two thirds of the work card's room; the card halves and so does
    // it, rather than coming back at a width the card no longer has.
    const sizes = tradeShares([15, 25, 40, 20], [false, false, true, false], 1, 3, 30, 5, 5)
    expect(sizes?.[2]).toBeCloseTo(20)
    expect(sizes?.[3]).toBeCloseTo(10)
    expect(sizes?.reduce((sum, size) => sum + size, 0)).toBeCloseTo(100)
  })

  it("keeps every other section on the screen where it was", () => {
    const hidden = [false, true, false, false]
    const before = drawn([10, 40, 30, 20], hidden)
    const after = drawn(tradeShares([10, 40, 30, 20], hidden, 0, 2, 6, 5, 5) ?? [], hidden)
    expect(after[0]).toBeCloseTo((before[0] ?? 0) + 6)
    expect(after[2]).toBeCloseTo((before[2] ?? 0) - 6)
    expect(after[3]).toBeCloseTo(before[3] ?? 0)
  })

  it("moves the room a section before took whole along with it", () => {
    const hidden = [false, false, true]
    const sizes = tradeShares([20, 28, 52], hidden, 0, 1, -10, 5, 5)
    const shares = drawn(sizes ?? [], hidden)
    expect(shares[0]).toBeCloseTo(10)
    expect(shares[1]).toBeCloseTo(90)
  })

  it("stops each side at its own minimum, measured as drawn", () => {
    const hidden = [false, false, true, false]
    const widened = drawn(tradeShares([15, 25, 40, 20], hidden, 1, 3, 100, 5, 8) ?? [], hidden)
    expect(widened[3]).toBeCloseTo(8)
    const narrowed = drawn(tradeShares([15, 25, 40, 20], hidden, 1, 3, -100, 5, 8) ?? [], hidden)
    expect(narrowed[1]).toBeCloseTo(5)
  })

  it("does not move a border that is already at the minimum", () => {
    expect(tradeShares([10, 90], [false, false], 0, 1, -5, 10, 10)).toEqual([10, 90])
  })

  it("answers nothing for a section the split does not have", () => {
    expect(tradeShares([10, 90], [false, false], 5, 1, -5, 10, 10)).toBeNull()
  })
})
