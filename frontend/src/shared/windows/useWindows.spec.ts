import { defineComponent } from "vue"
import { describe, expect, it } from "vitest"

import { first } from "@/shared/testing/collections"

import { useWindows } from "./useWindows"
import type { OpenWindow } from "./useWindows"

const Blank = defineComponent({ render: () => null })

function windowOf(id: string, title = id): OpenWindow {
  return { id, look: { title }, size: { width: 400, height: 300 }, component: Blank }
}

describe("opening windows", () => {
  it("shows one window per id", () => {
    const windows = useWindows()

    windows.open(windowOf("a"))
    windows.open(windowOf("b"))

    expect(windows.context.windows.value.map((entry) => entry.id)).toEqual(["a", "b"])
  })

  it("brings the existing one forward rather than opening a second", () => {
    // Two windows of one connection are two unsaved edits of one row, and
    // whichever is saved second silently wins.
    const windows = useWindows()
    windows.open(windowOf("a"))
    windows.open(windowOf("b"))

    windows.open(windowOf("a"))

    expect(windows.context.windows.value.map((entry) => entry.id)).toEqual(["b", "a"])
    expect(windows.context.frontId.value).toBe("a")
  })

  it("does not put a new window exactly on top of the last", () => {
    const windows = useWindows()
    windows.open(windowOf("a"))
    windows.open(windowOf("b"))

    const [a, b] = windows.context.windows.value
    expect(b?.rect.x).toBeGreaterThan(a?.rect.x ?? 0)
  })

  it("closes only the window asked for", () => {
    const windows = useWindows()
    windows.open(windowOf("a"))
    windows.open(windowOf("b"))

    windows.close("a")

    expect(windows.context.windows.value.map((entry) => entry.id)).toEqual(["b"])
    expect(windows.isOpen("a")).toBe(false)
  })
})

describe("a window whose id changes", () => {
  it("answers to the new id and no longer to the old", () => {
    const windows = useWindows()
    windows.open(windowOf("connector:new:1"))

    windows.rename("connector:new:1", "connector:7", { title: "prod" })

    expect(windows.isOpen("connector:7")).toBe(true)
    expect(windows.isOpen("connector:new:1")).toBe(false)
    expect(first(windows.context.windows.value).look.title).toBe("prod")
  })

  it("keeps the same key, so nothing is remounted", () => {
    // The bug this pins: the host keyed its list by id, so saving a draft
    // destroyed the window and built a fresh one — the form reset itself and
    // the close that followed the save reached an instance that was gone.
    const windows = useWindows()
    windows.open(windowOf("connector:new:1"))
    const before = first(windows.context.windows.value).key

    windows.rename("connector:new:1", "connector:7", { title: "prod" })

    expect(first(windows.context.windows.value).key).toBe(before)
  })

  it("keeps its place in the stack", () => {
    const windows = useWindows()
    windows.open(windowOf("a"))
    windows.open(windowOf("connector:new:1"))
    windows.context.focus("a")

    windows.rename("connector:new:1", "connector:7", { title: "prod" })

    expect(windows.context.windows.value.map((entry) => entry.id)).toEqual([
      "connector:7",
      "a",
    ])
  })

  it("can then be closed by the id it now has", () => {
    const windows = useWindows()
    windows.open(windowOf("connector:new:1"))
    windows.rename("connector:new:1", "connector:7", { title: "prod" })

    windows.close("connector:7")

    expect(windows.context.windows.value).toEqual([])
  })

  it("gives every window a key of its own", () => {
    const windows = useWindows()
    windows.open(windowOf("a"))
    windows.open(windowOf("b"))

    const keys = windows.context.windows.value.map((entry) => entry.key)
    expect(new Set(keys).size).toBe(2)
  })
})

describe("moving a window", () => {
  it("cannot be dragged out of reach", () => {
    const windows = useWindows()
    windows.open(windowOf("a"))

    windows.context.move("a", { x: 99999, y: 99999 })

    const rect = first(windows.context.windows.value).rect
    expect(rect.x).toBeLessThan(window.innerWidth)
    expect(rect.y).toBeLessThan(window.innerHeight)
  })
})
