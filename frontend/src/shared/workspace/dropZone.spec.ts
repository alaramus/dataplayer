import { describe, expect, it } from "vitest"

import { dropZoneAt } from "./dropZone"

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

  it("reads the rectangle's own origin rather than assuming zero", () => {
    expect(dropZoneAt({ left: 1000, top: 500, width: 400, height: 200 }, 1020, 600)).toBe("left")
  })

  it("answers the centre for a rectangle with no size", () => {
    expect(dropZoneAt({ left: 0, top: 0, width: 0, height: 0 }, 0, 0)).toBe("center")
  })
})
