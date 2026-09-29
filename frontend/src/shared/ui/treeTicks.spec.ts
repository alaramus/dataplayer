import { describe, expect, it } from "vitest"

import { leafKeys, tickStates, withTicks } from "./treeTicks"
import type { TickNode } from "./treeTicks"

const host: TickNode = {
  key: "host",
  children: [
    { key: "cpu", children: [{ key: "cpu.user" }, { key: "cpu.system" }] },
    { key: "memory" },
  ],
}

describe("tree ticks", () => {
  it("stand for the leaves under a node, however deep", () => {
    expect(leafKeys(host, "key")).toEqual(["cpu.user", "cpu.system", "memory"])
    expect(leafKeys({ key: "memory" }, "key")).toEqual(["memory"])
  })

  it("give a branch not read yet no box, and one whose children are read a box", () => {
    const states = tickStates(
      [{ key: "later", lazy: true }, { key: "read", lazy: true, children: [{ key: "a" }] }],
      "key",
      []
    )
    expect(states.has("later")).toBe(false)
    expect(states.get("read")).toBe(false)
  })

  it("tick a branch when all its leaves are, half when some are", () => {
    expect(tickStates([host], "key", []).get("host")).toBe(false)
    const some = tickStates([host], "key", ["cpu.user", "cpu.system"])
    expect(some.get("host")).toBeNull()
    expect(some.get("cpu")).toBe(true)
    expect(some.get("memory")).toBe(false)
    const all = tickStates([host], "key", ["cpu.user", "cpu.system", "memory"])
    expect(all.get("host")).toBe(true)
  })

  it("tick and untick a node's leaves and leave every other tick alone", () => {
    const leaves = leafKeys(host, "key")
    expect(withTicks(["elsewhere", "memory"], leaves, true)).toEqual([
      "elsewhere", "memory", "cpu.user", "cpu.system",
    ])
    expect(withTicks(["elsewhere", "memory", "cpu.user"], leaves, false)).toEqual(["elsewhere"])
  })
})
