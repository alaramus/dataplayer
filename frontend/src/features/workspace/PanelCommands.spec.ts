import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"
import { defineComponent, h, ref } from "vue"

import { freshnessOf } from "@/shared/freshness/freshness"
import type { Freshness } from "@/shared/freshness/freshness"
import AppIconButton from "@/shared/ui/AppIconButton.vue"
import { makeLeaf, workspaceKey } from "@/shared/workspace"
import type { PanelLook, WorkspaceContext } from "@/shared/workspace"

import PanelCommands from "./PanelCommands.vue"
import { createReloadRegistry, provideReloadRegistry } from "./reloadable"
import type { ReloadRegistry } from "./reloadable"
import { workspaceActionsKey } from "./state"
import type { WorkspaceActions } from "./state"

/**
 * The row of commands a panel keeps about itself (D112): the way back to its
 * node in a catalog, and the re-read. The way out of a window is not here — it
 * is about the frame, and stands in the window's own bar.
 *
 * The re-read absorbed the freshness badge, which stood beside it as a control
 * of its own and re-read the source when pressed. It is a mark now, "Live" or
 * a clock, riding above the reload; the age is in what is said on hover (D105).
 */

const REVEAL = { connectorId: "c1", nodeId: "public.orders", label: "orders" }
const PLAIN: PanelLook = { title: "orders", icon: "table_chart" }
const RELOADABLE: PanelLook = { ...PLAIN, reloadTooltip: "Re-read this table" }

const PanelBody = defineComponent({ setup: () => () => h("div", "rows") })

function contextFor(
  look: PanelLook,
  overrides: Partial<WorkspaceContext>
): WorkspaceContext {
  return {
    tree: ref(makeLeaf("work", ["p1"])),
    panelIds: ref(["p1"]),
    keyOf: (panelId) => panelId,
    detached: ref([]),
    focusedDetached: ref(null),
    focusedLeaf: ref(null),
    dragging: ref(null),
    lookOf: () => look,
    componentOf: () => PanelBody,
    emptyOf: () => null,
    admissionOf: () => ({ accepts: true, remaining: 1 }),
    collapsedOf: () => null,
    activate: () => undefined,
    canDetach: () => true,
    detach: () => undefined,
    dock: () => undefined,
    close: () => undefined,
    requestClose: async () => true,
    closeOthers: async () => undefined,
    focus: () => undefined,
    toggleCollapse: () => undefined,
    resize: () => undefined,
    press: () => undefined,
    pointerMoved: () => undefined,
    endDrag: () => undefined,
    ...overrides,
  }
}

/**
 * Mounted the way a panel holds it: inside something that provides the reload
 * registry, because that is what a panel registers into and what this presses.
 */
function mountCommands(
  options: {
    look?: PanelLook
    context?: Partial<WorkspaceContext>
    actions?: Partial<WorkspaceActions>
    reloads?: ReloadRegistry
    reveal?: typeof REVEAL
    freshness?: Freshness
    cacheTtlSeconds?: number | null
  } = {}
) {
  const registry = options.reloads ?? createReloadRegistry()
  const Host = defineComponent({
    setup() {
      provideReloadRegistry(registry)
      return () =>
        h(PanelCommands, {
          panelId: "p1",
          reveal: options.reveal,
          freshness: options.freshness,
          cacheTtlSeconds: options.cacheTtlSeconds,
        })
    },
  })

  return mount(Host, {
    global: {
      plugins: [Quasar],
      provide: {
        [workspaceKey as symbol]: contextFor(options.look ?? PLAIN, options.context ?? {}),
        [workspaceActionsKey as symbol]: {
          revealInCatalog: vi.fn(),
          ...options.actions,
        } as WorkspaceActions,
      },
    },
  })
}

describe("PanelCommands", () => {
  it("draws nothing at all outside a workspace", () => {
    // Every panel has a unit test that mounts it on its own. There is no tab
    // to return to and no look to read there, so this draws none of itself
    // rather than half of it.
    const wrapper = mount(PanelCommands, {
      global: { plugins: [Quasar] },
      props: { panelId: "p1", reveal: REVEAL },
    })

    expect(wrapper.find('[data-testid="panel-reveal"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="panel-reload"]').exists()).toBe(false)
  })

  it("shows the node this panel is a view of in the catalog", async () => {
    const revealInCatalog = vi.fn()
    const wrapper = mountCommands({ actions: { revealInCatalog }, reveal: REVEAL })

    await wrapper.get('[data-testid="panel-reveal"]').trigger("click")

    expect(revealInCatalog).toHaveBeenCalledWith("c1", "public.orders", "orders")
  })

  it("offers no way to a catalog for a panel that is a view of no node", () => {
    // A chart, a console, a captured result. The button is absent rather than
    // present and inert: a press with nothing behind it is the defect this
    // whole arrangement replaced.
    expect(mountCommands().find('[data-testid="panel-reveal"]').exists()).toBe(false)
  })

  it("re-reads the panel through what the panel itself registered", async () => {
    const reloads = createReloadRegistry()
    const read = vi.fn()
    reloads.register("p1", read)
    const wrapper = mountCommands({ look: RELOADABLE, reloads })

    await wrapper.get('[data-testid="panel-reload"]').trigger("click")

    expect(read).toHaveBeenCalledTimes(1)
  })

  it("says what re-reading this panel means, in the panel's own words", () => {
    const wrapper = mountCommands({ look: RELOADABLE })

    expect(wrapper.get('[data-testid="panel-reload"]').attributes("aria-label")).toBe(
      "Re-read this table"
    )
  })

  it("draws no reload for a panel with nothing to re-read", () => {
    expect(mountCommands().find('[data-testid="panel-reload"]').exists()).toBe(false)
  })

  it("carries no mark where the source keeps nothing", () => {
    // Nothing it shows could be older than the read, so there is nothing to
    // report and the button is the icon every other command in the row is.
    const wrapper = mountCommands({ look: RELOADABLE })

    expect(wrapper.find('[data-testid="panel-freshness"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="panel-reload"]').get(".q-icon").text()).toBe(
      "refresh"
    )
  })

  it("says the page is live while the answer is the read", () => {
    const wrapper = mountCommands({
      look: RELOADABLE,
      freshness: freshnessOf({ "x-data-cache": "miss" }),
    })
    const mark = wrapper.get('[data-testid="panel-freshness"]')

    expect(mark.attributes("data-live")).toBe("yes")
    expect(mark.text()).toBe("Live")
    // The button beside the mark never changes: it is the reload, one icon and
    // one width, whatever stands next to it.
    expect(wrapper.get('[data-testid="panel-reload"]').get(".q-icon").text()).toBe(
      "refresh"
    )
  })

  it("shows a clock instead once the answer is one that was kept", () => {
    const wrapper = mountCommands({
      look: RELOADABLE,
      freshness: freshnessOf({ "x-data-cache": "hit", "x-data-cache-age": "20" }),
      cacheTtlSeconds: 300,
    })
    const mark = wrapper.get('[data-testid="panel-freshness"]')

    expect(mark.attributes("data-live")).toBe("no")
    expect(mark.text()).toBe("schedule")
    expect(wrapper.get('[data-testid="panel-reload"]').get(".q-icon").text()).toBe(
      "refresh"
    )
  })

  it("stops calling a page live once it has aged on screen", () => {
    // The reply said it was a read of the source. Four minutes later that is
    // still true and no longer the point.
    const wrapper = mountCommands({
      look: RELOADABLE,
      freshness: freshnessOf({ "x-data-cache": "miss" }, Date.now() - 240_000),
    })

    expect(wrapper.get('[data-testid="panel-freshness"]').attributes("data-live")).toBe(
      "no"
    )
  })

  it("keeps the age out of the row and in what is said on hovering", () => {
    // A control whose width follows the age of a page moves while the row is
    // being read. Whether this may be stale is a glance; how stale is a
    // question, and the answer is one hover away (D105).
    const wrapper = mountCommands({
      look: RELOADABLE,
      freshness: freshnessOf({ "x-data-cache": "hit", "x-data-cache-age": "20" }),
      cacheTtlSeconds: 300,
    })

    expect(wrapper.text()).not.toContain("20s")
    expect(wrapper.getComponent(AppIconButton).props("tooltip")).toBe(
      "Read from the source 20s ago. This connection keeps answers for 5m. " +
        "Re-read this table."
    )
  })

  it("re-reads from the button under the mark", async () => {
    const reloads = createReloadRegistry()
    const read = vi.fn()
    reloads.register("p1", read)
    const wrapper = mountCommands({
      look: RELOADABLE,
      reloads,
      freshness: freshnessOf({ "x-data-cache": "hit", "x-data-cache-age": "20" }),
    })

    await wrapper.get('[data-testid="panel-reload"]').trigger("click")

    expect(read).toHaveBeenCalledTimes(1)
  })

  it("leaves the way out of a window to the window", () => {
    // Detached or docked, this row says nothing about the frame: returning a
    // panel stands with minimize and close, where somebody looks for it.
    const floating = mountCommands({
      context: {
        detached: ref([
          { panelId: "p1", leafId: "work", at: 0, accepts: "work", fallbackLeafId: "work" },
        ]),
      },
    })

    expect(floating.find('[data-testid="dock-panel"]').exists()).toBe(false)
  })
})
