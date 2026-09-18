import { describe, expect, it } from "vitest"

import { railRules } from "./railRules"

describe("the lines of the dashboards rail", () => {
  it("stand between the groups that show something", () => {
    expect(railRules(2, 1)).toEqual({ beforeShared: true, beforeSources: true })
    expect(railRules(2, 0)).toEqual({ beforeShared: false, beforeSources: true })
    expect(railRules(0, 1)).toEqual({ beforeShared: false, beforeSources: true })
  })

  it("leave the sources undivided while there is no dashboard", () => {
    expect(railRules(0, 0)).toEqual({ beforeShared: false, beforeSources: false })
  })
})
