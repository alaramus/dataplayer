import { defineComponent, effectScope } from "vue"
import type { EffectScope } from "vue"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { first } from "@/shared/testing/collections"

import { useWindows } from "./useWindows"
import type { OpenWindow, WindowsApi } from "./useWindows"

const Blank = defineComponent({ render: () => null })

// useWindows listens to the viewport and lets go when its scope ends; called
// bare, it has no scope and Vue warns that the listener is never removed.
const scopes: EffectScope[] = []

function scopedWindows(): WindowsApi {
  const scope = effectScope()
  scopes.push(scope)
  const windows = scope.run(useWindows)
  if (!windows) throw new Error("the scope did not run")
  return windows
}

afterEach(() => {
  for (const scope of scopes.splice(0)) scope.stop()
})

function windowOf(id: string, title = id): OpenWindow {
  return { id, look: { title }, size: { width: 400, height: 300 }, component: Blank }
}

describe("opening windows", () => {
  it("shows one window per id", () => {
    const windows = scopedWindows()

    windows.open(windowOf("a"))
    windows.open(windowOf("b"))

    expect(windows.context.windows.value.map((entry) => entry.id)).toEqual(["a", "b"])
  })

  it("brings the existing one forward rather than opening a second", () => {
    // Two windows of one connection are two unsaved edits of one row, and
    // whichever is saved second silently wins.
    const windows = scopedWindows()
    windows.open(windowOf("a"))
    windows.open(windowOf("b"))

    windows.open(windowOf("a"))

    expect(windows.context.windows.value.map((entry) => entry.id)).toEqual(["b", "a"])
    expect(windows.context.frontId.value).toBe("a")
  })

  it("does not put a new window exactly on top of the last", () => {
    const windows = scopedWindows()
    windows.open(windowOf("a"))
    windows.open(windowOf("b"))

    const [a, b] = windows.context.windows.value
    expect(b?.rect.x).toBeGreaterThan(a?.rect.x ?? 0)
  })

  it("closes only the window asked for", () => {
    const windows = scopedWindows()
    windows.open(windowOf("a"))
    windows.open(windowOf("b"))

    windows.close("a")

    expect(windows.context.windows.value.map((entry) => entry.id)).toEqual(["b"])
    expect(windows.isOpen("a")).toBe(false)
  })
})

describe("a window whose subject changes while it is open", () => {
  it("says the new heading without being reopened", () => {
    const windows = scopedWindows()
    windows.open(windowOf("dialog:create"))
    const before = first(windows.context.windows.value).key

    windows.retitle("dialog:create", { title: "Save this data as a file" })

    expect(first(windows.context.windows.value).look.title).toBe(
      "Save this data as a file"
    )
    // The same window, so a form in it keeps everything typed into it.
    expect(first(windows.context.windows.value).key).toBe(before)
  })

  it("ignores a window that is not open", () => {
    const windows = scopedWindows()
    windows.open(windowOf("a"))

    windows.retitle("gone", { title: "nothing" })

    expect(first(windows.context.windows.value).look.title).toBe("a")
  })
})

describe("a window whose id changes", () => {
  it("answers to the new id and no longer to the old", () => {
    const windows = scopedWindows()
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
    const windows = scopedWindows()
    windows.open(windowOf("connector:new:1"))
    const before = first(windows.context.windows.value).key

    windows.rename("connector:new:1", "connector:7", { title: "prod" })

    expect(first(windows.context.windows.value).key).toBe(before)
  })

  it("keeps its place in the stack", () => {
    const windows = scopedWindows()
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
    const windows = scopedWindows()
    windows.open(windowOf("connector:new:1"))
    windows.rename("connector:new:1", "connector:7", { title: "prod" })

    windows.close("connector:7")

    expect(windows.context.windows.value).toEqual([])
  })

  it("gives every window a key of its own", () => {
    const windows = scopedWindows()
    windows.open(windowOf("a"))
    windows.open(windowOf("b"))

    const keys = windows.context.windows.value.map((entry) => entry.key)
    expect(new Set(keys).size).toBe(2)
  })
})

describe("moving a window", () => {
  it("cannot be dragged out of reach", () => {
    const windows = scopedWindows()
    windows.open(windowOf("a"))

    windows.context.move("a", { x: 99999, y: 99999 })

    const rect = first(windows.context.windows.value).rect
    expect(rect.x).toBeLessThan(window.innerWidth)
    expect(rect.y).toBeLessThan(window.innerHeight)
  })

  it("stores a user resize", () => {
    const windows = scopedWindows()
    windows.open(windowOf("a"))

    windows.context.resize("a", "bottom-right", { x: 900, y: 700 })

    const rect = first(windows.context.windows.value).rect
    expect(rect.width).toBeGreaterThan(400)
    expect(rect.height).toBeGreaterThan(300)
  })
})

describe("content-sized windows", () => {
  it("keeps following content that changes after the first measurement", () => {
    const windows = scopedWindows()
    windows.open(windowOf("a"))

    windows.context.fit("a", { width: 400, height: 220 })
    windows.context.fit("a", { width: 400, height: 480 })

    expect(first(windows.context.windows.value).rect.height).toBe(480)
  })

  it("stops automatic fitting after the user resizes the window", () => {
    const windows = scopedWindows()
    windows.open(windowOf("a"))
    windows.context.resize("a", "bottom-right", { x: 700, y: 600 })
    const chosen = first(windows.context.windows.value).rect.height

    windows.context.fit("a", { width: 400, height: 200 })

    expect(first(windows.context.windows.value).rect.height).toBe(chosen)
  })
})

describe("stable windows", () => {
  it("keeps the footer in the viewport when opening after a shorter window", () => {
    const scope = effectScope()
    scope.run(() => {
      const windows = useWindows()
      windows.open(windowOf("catalog"))
      windows.open({ ...windowOf("stable"), sizing: "stable", size: { width: 560, height: 660 } })
      const rect = windows.context.windows.value.find((entry) => entry.id === "stable")!.rect
      expect(rect.y + rect.height).toBeLessThanOrEqual(window.innerHeight)
    })
    scope.stop()
  })

  it("ignores content measurements before and after a manual resize and maximize", () => {
    const scope = effectScope()
    scope.run(() => {
      const windows = useWindows()
      windows.open({ ...windowOf("stable"), sizing: "stable" })
      const initial = { ...first(windows.context.windows.value).rect }
      windows.context.fit("stable", { width: 900, height: 700 })
      windows.context.fit("stable", { width: 200, height: 100 })
      expect(first(windows.context.windows.value).rect).toEqual(initial)

      windows.context.resize("stable", "bottom-right", { x: 900, y: 700 })
      const chosen = { ...first(windows.context.windows.value).rect }
      expect(chosen).not.toEqual(initial)
      windows.context.toggleMaximize("stable")
      windows.context.fit("stable", { width: 200, height: 100 })
      windows.context.toggleMaximize("stable")
      windows.context.fit("stable", { width: 200, height: 100 })
      expect(first(windows.context.windows.value).rect).toEqual(chosen)
    })
    scope.stop()
  })

  it("bounds the opening rectangle and constrains it when the viewport shrinks", () => {
    const scope = effectScope()
    try {
      vi.stubGlobal("innerWidth", 800)
      vi.stubGlobal("innerHeight", 600)
      scope.run(() => {
        const windows = useWindows()
        windows.open({ ...windowOf("stable"), sizing: "stable", size: { width: 900, height: 700 } })
        expect(first(windows.context.windows.value).rect).toEqual({ x: 0, y: 0, width: 800, height: 600 })
        vi.stubGlobal("innerWidth", 360)
        vi.stubGlobal("innerHeight", 480)
        window.dispatchEvent(new Event("resize"))
        expect(first(windows.context.windows.value).rect).toEqual({ x: 0, y: 0, width: 360, height: 480 })
      })
    } finally {
      scope.stop()
      vi.unstubAllGlobals()
    }
  })
})

describe("minimized and maximized windows", () => {
  let scope: ReturnType<typeof effectScope>
  let windows: WindowsApi

  beforeEach(() => {
    scope = effectScope()
    scope.run(() => { windows = useWindows() })
  })

  afterEach(() => {
    scope.stop()
    vi.unstubAllGlobals()
  })

  it("puts a window aside without closing it and reveals the next visible window", () => {
    const beforeClose = vi.fn(() => false)
    const onClosed = vi.fn()
    windows.open(windowOf("a"))
    windows.open({ ...windowOf("b"), beforeClose, onClosed })
    const original = windows.context.windows.value.find((entry) => entry.id === "b")

    windows.context.minimize("b")
    expect(windows.context.frontId.value).toBe("a")
    expect(windows.isOpen("b")).toBe(true)
    expect(beforeClose).not.toHaveBeenCalled()
    expect(onClosed).not.toHaveBeenCalled()

    windows.context.minimize("a")
    expect(windows.context.frontId.value).toBeNull()

    windows.open(windowOf("b"))
    expect(windows.context.windows.value).toHaveLength(2)
    expect(windows.context.frontId.value).toBe("b")
    expect(windows.context.windows.value.find((entry) => entry.id === "b")).toEqual({
      ...original, minimized: false,
    })
  })

  it("restores the chosen size after maximizing, minimizing and reopening", () => {
    windows.open(windowOf("a"))
    windows.context.resize("a", "bottom-right", { x: 800, y: 650 })
    const normal = first(windows.context.windows.value)

    windows.context.toggleMaximize("a")
    windows.context.minimize("a")
    windows.open(windowOf("a"))
    expect(first(windows.context.windows.value).maximized).toBe(true)

    windows.context.toggleMaximize("a")
    expect(first(windows.context.windows.value)).toEqual(normal)
  })

  it.each(["minimized", "maximized"] as const)(
    "ignores hidden measurements and geometry gestures while %s",
    (mode) => {
      windows.open(windowOf("a"))
      windows.context.fit("a", { width: 440, height: 320 })
      const normal = first(windows.context.windows.value)
      if (mode === "minimized") windows.context.minimize("a")
      else windows.context.toggleMaximize("a")

      windows.context.fit("a", { width: 1500, height: 0 })
      windows.context.move("a", { x: 0, y: 0 })
      windows.context.resize("a", "bottom-right", { x: 300, y: 160 })
      expect(first(windows.context.windows.value).rect).toEqual(normal.rect)
      expect(first(windows.context.windows.value).autoFit).toBe(true)

      if (mode === "minimized") windows.context.focus("a")
      else windows.context.toggleMaximize("a")
      windows.context.fit("a", { width: 440, height: 380 })
      expect(first(windows.context.windows.value).rect.height).toBe(380)
    }
  )

  it("keeps the normal window reachable after the viewport shrinks while maximized", () => {
    windows.open(windowOf("a"))
    windows.context.move("a", { x: 700, y: 600 })
    windows.context.toggleMaximize("a")

    vi.stubGlobal("innerWidth", 500)
    vi.stubGlobal("innerHeight", 400)
    window.dispatchEvent(new Event("resize"))
    windows.context.toggleMaximize("a")

    const rect = first(windows.context.windows.value).rect
    expect(rect.x).toBeLessThanOrEqual(380)
    expect(rect.y).toBeLessThanOrEqual(280)
    expect(rect.width).toBe(400)
  })

  it("keeps the usual close confirmation after a minimized window is restored", async () => {
    const beforeClose = vi.fn(() => false)
    const onClosed = vi.fn()
    windows.open({ ...windowOf("a"), beforeClose, onClosed })
    windows.context.minimize("a")
    windows.context.focus("a")

    await windows.context.requestClose("a")
    expect(windows.isOpen("a")).toBe(true)
    expect(onClosed).not.toHaveBeenCalled()

    beforeClose.mockReturnValue(true)
    await windows.context.requestClose("a")
    expect(windows.context.windows.value).toEqual([])
    expect(windows.context.frontId.value).toBeNull()
    expect(onClosed).toHaveBeenCalledOnce()
  })
})
