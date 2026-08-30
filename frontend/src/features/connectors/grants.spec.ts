import { describe, expect, it } from "vitest"

import type { UserBrief } from "@/client"
import { offerable } from "./grants"

const directory: UserBrief[] = [
  { id: "1", email: "ada@example.com", full_name: "Ada" },
  { id: "2", email: "grace@example.com", full_name: null },
]

describe("offerable", () => {
  it("leaves out everybody who already holds a level", () => {
    // Their level is changed on their own row; offering them again would be a
    // second way to do the same thing, and the two could disagree.
    expect(offerable(directory, [{ user_id: "1" }]).map((user) => user.id)).toEqual(["2"])
  })

  it("offers everybody when nothing has been given away", () => {
    expect(offerable(directory, [])).toHaveLength(2)
  })

  it("offers nobody when everybody holds something", () => {
    expect(offerable(directory, [{ user_id: "1" }, { user_id: "2" }])).toEqual([])
  })
})
