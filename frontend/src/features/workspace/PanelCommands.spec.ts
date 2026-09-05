import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it, vi } from "vitest"
import { defineComponent, h, ref } from "vue"

import { makeLeaf, workspaceKey } from "@/shared/workspace"
import type { PanelLook, WorkspaceContext } from "@/shared/workspace"

import PanelCommands from "./PanelCommands.vue"
import { createReloadRegistry, provideReloadRegistry } from "./reloadable"
import type { ReloadRegistry } from "./reloadable"
import { workspaceActionsKey } from "./state"
import type { WorkspaceActions } from "./state"

/**
 * The row of commands a panel keeps about itself (D112).
 *
 * Three things the chrome around a panel used to draw: the way back to the
 * node in a catalog, which was a click on the icon of the tab; the re-read,
 * which was a second button on the tab; and the way out of a window, which was
 * a strip of its own above a panel that already draws a row of buttons.
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
  } = {}
) {
  const registry = options.reloads ?? createReloadRegistry()
  const Host = defineComponent({
    setup() {
      provideReloadRegistry(registry)
      return () => h(PanelCommands, { panelId: "p1", reveal: options.reveal })
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

  it("offers the way back only while the panel is in a window of its own", async () => {
    const dock = vi.fn()
    expect(mountCommands({ context: { dock } }).find('[data-testid="dock-panel"]').exists()).toBe(
      false
    )

    const floating = mountCommands({
      context: {
        dock,
        detached: ref([
          { panelId: "p1", leafId: "work", at: 0, accepts: "work", fallbackLeafId: "work" },
        ]),
      },
    })
    await floating.get('[data-testid="dock-panel"]').trigger("click")

    expect(dock).toHaveBeenCalledWith("p1")
  })
})
