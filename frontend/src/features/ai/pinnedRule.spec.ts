import { describe, expect, it } from "vitest"

import { pinnedRuleBefore } from "./pinnedRule"

const chats = (...pinned: boolean[]) => pinned.map((one) => ({ chat: { pinned: one } }))

describe("the line under the pinned chats", () => {
  it("stands before the first chat that is not pinned, and nowhere else", () => {
    const group = chats(true, true, false, false)
    expect([0, 1, 2, 3].map((index) => pinnedRuleBefore(group, index))).toEqual([false, false, true, false])
  })

  it("is not drawn when the group is all pinned or none of it is", () => {
    expect([0, 1].map((index) => pinnedRuleBefore(chats(true, true), index))).toEqual([false, false])
    expect([0, 1].map((index) => pinnedRuleBefore(chats(false, false), index))).toEqual([false, false])
  })
})
