/* eslint-disable vue/one-component-per-file -- a panel and the host that provides its registry, not components of the application. */
import { mount } from "@vue/test-utils"
import { defineComponent, h, nextTick, ref } from "vue"
import { describe, expect, it, vi } from "vitest"

import {
  createReloadRegistry,
  provideReloadRegistry,
  useReloadable,
} from "@/features/workspace/reloadable"

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

  // A panel is named by what it holds, and a console put into the library is
  // renamed where it stands without being built again (D65). Registered under
  // the name it had at setup, it answered to nothing afterwards: the button
  // was drawn, was pressed, and did nothing at all.
  it("follows a panel that is renamed where it stands", async () => {
    const registry = createReloadRegistry()
    const reload = vi.fn()
    const panelId = ref("query:draft:d9")

    const Panel = defineComponent({
      props: { panelId: { type: String, required: true } },
      setup(props) {
        useReloadable(() => props.panelId, reload)
        return () => h("div")
      },
    })
    const Host = defineComponent({
      setup() {
        provideReloadRegistry(registry)
        return () => h(Panel, { panelId: panelId.value })
      },
    })
    mount(Host)

    panelId.value = "query:doc-9"
    await nextTick()

    await expect(registry.reload("query:doc-9")).resolves.toBe(true)
    expect(reload).toHaveBeenCalledOnce()
    // And only under the name it has now: the old one is nobody's.
    await expect(registry.reload("query:draft:d9")).resolves.toBe(false)
  })
})
