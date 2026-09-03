import { describe, expect, it } from "vitest"

import { dropShape, dropZoneAt, dropZoneFor, insertionAt } from "./dropZone"

/** A wide section: a strip across the top, the body under it. */
const wide = {
  strip: { left: 0, top: 0, width: 400, height: 30 },
  body: { left: 0, top: 30, width: 400, height: 200 },
}

/** A tall one, for the rule that decides a tie. */
const tall = {
  strip: { left: 0, top: 0, width: 200, height: 30 },
  body: { left: 0, top: 30, width: 200, height: 400 },
}

describe("where in a strip a tab would land", () => {
  const strip = (widths: number[]) => {
    let left = 0
    return widths.map((width) => {
      const tab = { left, top: 0, width, height: 28 }
      left += width
      return tab
    })
  }

  it("claims a tab by whichever half of it the pointer is in", () => {
    // The mark moves as the pointer passes the middle of a tab rather than
    // its edge, which is what makes it possible to aim between two of them.
    const tabs = strip([100, 100, 100])

    expect(insertionAt(tabs, 10)).toBe(0)
    expect(insertionAt(tabs, 49)).toBe(0)
    expect(insertionAt(tabs, 51)).toBe(1)
    expect(insertionAt(tabs, 149)).toBe(1)
    expect(insertionAt(tabs, 151)).toBe(2)
  })

  it("puts a tab past the last one at the end", () => {
    expect(insertionAt(strip([100, 100]), 400)).toBe(2)
  })

  it("puts the first tab of an empty strip first", () => {
    expect(insertionAt([], 0)).toBe(0)
  })
})

describe("the zone a pointer is over", () => {
  it("is the centre anywhere in the strip of tabs", () => {
    // The strip is the one way to put a panel beside the others, and it is
    // the whole of that way: a tab is landed on the head, not in the middle
    // of what the head is above. See G3.
    expect(dropZoneAt(wide, 200, 15)).toBe("center")
    expect(dropZoneAt(wide, 5, 2)).toBe("center")
    expect(dropZoneAt(wide, 395, 28)).toBe("center")
  })

  it("is the nearest edge in the body, with nothing neutral in between", () => {
    expect(dropZoneAt(wide, 20, 130)).toBe("left")
    expect(dropZoneAt(wide, 380, 130)).toBe("right")
    expect(dropZoneAt(wide, 200, 40)).toBe("top")
    expect(dropZoneAt(wide, 200, 220)).toBe("bottom")
  })

  it("measures nearness as a share of the side, not in pixels", () => {
    // Sixty pixels from the left of a body four hundred wide is less than a
    // sixth; fifty from the top of one two hundred tall is a quarter. In
    // pixels the top is nearer and would win, which on a wide section hands
    // it most of the panel.
    expect(dropZoneAt(wide, 60, 80)).toBe("left")
  })

  it("gives the middle of the body to the wider side", () => {
    // A tie, and the rule that settles it is the one already written for a
    // corner: on a wide section, splitting sideways is the likelier meaning.
    expect(dropZoneAt(wide, 200, 130)).toBe("left")
    expect(dropZoneAt(tall, 100, 230)).toBe("top")
  })

  it("reads the rectangles' own origins rather than assuming zero", () => {
    const moved = {
      strip: { left: 1000, top: 500, width: 400, height: 30 },
      body: { left: 1000, top: 530, width: 400, height: 200 },
    }
    expect(dropZoneAt(moved, 1200, 515)).toBe("center")
    expect(dropZoneAt(moved, 1020, 630)).toBe("left")
  })

  it("answers the centre for a section with no size", () => {
    const nothing = {
      strip: { left: 0, top: 0, width: 0, height: 0 },
      body: { left: 0, top: 0, width: 0, height: 0 },
    }
    expect(dropZoneAt(nothing, 0, 0)).toBe("center")
  })

  it("answers the centre for a section that is all strip and no body", () => {
    // A section pushed aside is forty pixels of handles: there is nothing to
    // divide, and everything in it means "put it here".
    const collapsed = {
      strip: { left: 0, top: 0, width: 40, height: 30 },
      body: { left: 0, top: 30, width: 40, height: 0 },
    }
    expect(dropZoneAt(collapsed, 20, 40)).toBe("center")
  })
})

describe("what a section will take", () => {
  const anywhere = { accepts: true, remaining: 1 }

  it("refuses every zone of a section that takes another role", () => {
    expect(dropZoneFor(wide, 200, 130, { accepts: false, remaining: 1 })).toBeNull()
    expect(dropZoneFor(wide, 200, 15, { accepts: false, remaining: 1 })).toBeNull()
  })

  it("keeps the zone the pointer is over when the roles agree", () => {
    expect(dropZoneFor(wide, 20, 130, anywhere)).toBe("left")
    expect(dropZoneFor(wide, 200, 15, anywhere)).toBe("center")
  })

  it("offers the centre instead of a side when the split would leave nothing behind", () => {
    // The only tab of a section dragged into its own body, and anything at
    // all dragged into the body of an empty one: one rule, two cases. See P3.
    expect(dropZoneFor(wide, 20, 130, { accepts: true, remaining: 0 })).toBe("center")
    expect(dropZoneFor(wide, 200, 220, { accepts: true, remaining: 0 })).toBe("center")
  })

  it("still takes it as a tab when there would be nothing left", () => {
    expect(dropZoneFor(wide, 200, 15, { accepts: true, remaining: 0 })).toBe("center")
  })
})

describe("what the highlight shows", () => {
  it("shows nothing where nothing is offered", () => {
    expect(dropShape(null, false)).toBe("none")
  })

  it("shows the strip when the panel would join the tabs there", () => {
    // The panel ends up in the head, so the head is what lights up: a whole
    // panel lit for a tab describes a result that will not happen. See G5.
    expect(dropShape("center", false)).toBe("strip")
  })

  it("shows the whole section when the panel would fill it", () => {
    expect(dropShape("center", true)).toBe("whole")
  })

  it("shows the half a split would give it", () => {
    expect(dropShape("left", false)).toBe("half")
    expect(dropShape("bottom", false)).toBe("half")
  })
})
