import { describe, expect, it, vi } from "vitest"

import { createReloadRegistry } from "@/features/workspace/reloadable"

describe("who knows how to re-read a panel", () => {
  it("calls what the panel registered", async () => {
    const registry = createReloadRegistry()
    const reload = vi.fn()
    registry.register("catalog:c1", reload)

    await registry.reload("catalog:c1")

    expect(reload).toHaveBeenCalledOnce()
  })

  it("waits for a reload that takes time", async () => {
    const registry = createReloadRegistry()
    const order: string[] = []
    registry.register("rows:t1", async () => {
      await Promise.resolve()
      order.push("finished")
    })

    await registry.reload("rows:t1")
    order.push("returned")

    expect(order).toEqual(["finished", "returned"])
  })

  it("stops calling a panel that took itself back", async () => {
    const registry = createReloadRegistry()
    const reload = vi.fn()
    const forget = registry.register("catalog:c1", reload)

    forget()
    await registry.reload("catalog:c1")

    expect(reload).not.toHaveBeenCalled()
  })

  // A tab restored from storage and never opened has never mounted, so nothing
  // is registered for it. Pressing reload must not throw, and the caller has to
  // be able to tell — showing the tab is what re-reads a panel that never read
  // anything.
  it("says nothing was registered rather than failing", async () => {
    const registry = createReloadRegistry()

    await expect(registry.reload("catalog:never-opened")).resolves.toBe(false)
  })

  it("says it did the work when something was registered", async () => {
    const registry = createReloadRegistry()
    registry.register("catalog:c1", () => {})

    await expect(registry.reload("catalog:c1")).resolves.toBe(true)
  })

  // Remounting replaces rather than adds: two copies would re-read twice, and
  // the older one belongs to a component that is gone.
  it("keeps only the latest registration for a panel", async () => {
    const registry = createReloadRegistry()
    const older = vi.fn()
    const newer = vi.fn()
    registry.register("catalog:c1", older)
    registry.register("catalog:c1", newer)

    await registry.reload("catalog:c1")

    expect(older).not.toHaveBeenCalled()
    expect(newer).toHaveBeenCalledOnce()
  })

  // Taking back a registration that has already been replaced would leave the
  // panel that is actually on screen unable to be re-read.
  it("does not let a replaced registration take the new one away", async () => {
    const registry = createReloadRegistry()
    const newer = vi.fn()
    const forgetOlder = registry.register("catalog:c1", () => {})
    registry.register("catalog:c1", newer)

    forgetOlder()
    await registry.reload("catalog:c1")

    expect(newer).toHaveBeenCalledOnce()
  })
})
