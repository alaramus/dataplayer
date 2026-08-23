import { describe, expect, it } from "vitest"

import { dropZoneAt, dropZoneFor } from "./dropZone"

const rect = { left: 0, top: 0, width: 400, height: 200 }

describe("the zone a pointer is over", () => {
  it("is the centre in the middle", () => {
    expect(dropZoneAt(rect, 200, 100)).toBe("center")
  })

  it("is the left edge within a quarter of the width", () => {
    expect(dropZoneAt(rect, 20, 100)).toBe("left")
  })

  it("is the right edge past three quarters", () => {
    expect(dropZoneAt(rect, 380, 100)).toBe("right")
  })

  it("is the top edge within a quarter of the height", () => {
    expect(dropZoneAt(rect, 200, 10)).toBe("top")
  })

  it("is the bottom edge past three quarters", () => {
    expect(dropZoneAt(rect, 200, 190)).toBe("bottom")
  })

  it("prefers the horizontal edge in a corner, because the wider side wins", () => {
    expect(dropZoneAt(rect, 10, 10)).toBe("left")
  })

  it("prefers the vertical edge in the corner of a tall rectangle", () => {
    // The wide case on its own would pass against a rule that always picks
    // the horizontal edge, which is the rule this test exists to rule out.
    expect(dropZoneAt({ left: 0, top: 0, width: 200, height: 400 }, 10, 10)).toBe("top")
  })

  it("treats the quarter mark itself as the middle rather than the edge", () => {
    expect(dropZoneAt(rect, 100, 100)).toBe("center")
  })

  it("reads the rectangle's own origin rather than assuming zero", () => {
    expect(dropZoneAt({ left: 1000, top: 500, width: 400, height: 200 }, 1020, 600)).toBe("left")
  })

  it("answers the centre for a rectangle with no size", () => {
    expect(dropZoneAt({ left: 0, top: 0, width: 0, height: 0 }, 0, 0)).toBe("center")
  })
})

describe("what a section will take", () => {
  const anywhere = { accepts: true, remaining: 1 }

  it("refuses every zone of a section that takes another role", () => {
    expect(dropZoneFor(rect, 200, 100, { accepts: false, remaining: 1 })).toBeNull()
    expect(dropZoneFor(rect, 20, 100, { accepts: false, remaining: 1 })).toBeNull()
  })

  it("keeps the zone the pointer is over when the roles agree", () => {
    expect(dropZoneFor(rect, 20, 100, anywhere)).toBe("left")
    expect(dropZoneFor(rect, 200, 100, anywhere)).toBe("center")
  })

  it("offers the centre instead of a side when the split would leave nothing behind", () => {
    // The only tab of a section dragged to its own edge, and anything at all
    // dragged to the edge of an empty one: one rule, two cases. See P3.
    expect(dropZoneFor(rect, 20, 100, { accepts: true, remaining: 0 })).toBe("center")
    expect(dropZoneFor(rect, 200, 190, { accepts: true, remaining: 0 })).toBe("center")
  })

  it("still takes it as a tab when there would be nothing left", () => {
    expect(dropZoneFor(rect, 200, 100, { accepts: true, remaining: 0 })).toBe("center")
  })
})
