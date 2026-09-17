import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"
import { defineComponent, h, ref } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { makeLeaf, makeSplit } from "./model"
import WorkspaceNode from "./WorkspaceNode.vue"
import { createPanelTargets, panelTargetsKey } from "./panelTargets"

/* eslint-disable vue/one-component-per-file -- two stand-ins for panel bodies, not components of the application. */
const Stub = defineComponent({ setup: () => () => h("div", { class: "stub" }, "panel body") })
const Hint = defineComponent({ setup: () => () => h("div", { class: "hint" }, "pick a table") })

/** Three columns: one holding a panel, one with nothing to say, one with a hint. */
const columns = () =>
  makeSplit(
    "root",
    "row",
    [
      makeLeaf("sources", ["p1"], { accepts: "sources", pinned: true }),
      makeLeaf("navigate", [], { accepts: "navigate", pinned: true }),
      makeLeaf("work", [], { accepts: "work", pinned: true }),
    ],
    [20, 28, 52]
  )

function contextFor(): WorkspaceContext {
  return {
    tree: ref(columns()),
    panelIds: ref(["p1", "p2"]),
    keyOf: (panelId) => panelId,
    detached: ref([]),
    focusedDetached: ref(null),
    focusedLeaf: ref(null),
    dragging: ref(null),
    lookOf: (panelId) => ({ title: `title ${panelId}`, icon: "square" }),
    componentOf: () => Stub,
    // The middle column has no empty view of its own: a column appears with
    // what goes in it. See P5.
    emptyOf: (accepts) => (accepts === "work" ? Hint : null),
    admissionOf: () => ({ accepts: true, remaining: 1 }),
    collapsedOf: () => null,
    sectionLookOf: () => ({ title: "Section", icon: "square" }),
    aside: ref([]),
    activate: () => undefined,
    canDetach: () => true,
    detach: () => undefined,
    dock: () => undefined,
    close: () => undefined,
    requestClose: async () => true,
    closeOthers: async () => undefined,
    focus: () => undefined,
    toggleCollapse: () => undefined,
    firstLeafId: ref(null),
    hideFirstCollapse: false,
    putAside: () => undefined,
    bringBack: () => undefined,
    resize: () => undefined,
    press: () => undefined,
    pointerMoved: () => undefined,
    endDrag: () => undefined,
  }
}

function mountColumns() {
  return mount(WorkspaceNode, {
    props: { node: columns() },
    global: { plugins: [Quasar], provide: {
      [workspaceKey as symbol]: contextFor(), [panelTargetsKey as symbol]: createPanelTargets(),
    } },
  })
}

describe("a split with a column that has nothing to show", () => {
  it("leaves that column off the screen entirely", () => {
    expect(mountColumns().find('[data-testid="workspace-leaf-navigate"]').exists()).toBe(false)
  })

  it("keeps the columns that do have something", () => {
    const wrapper = mountColumns()
    expect(wrapper.find('[data-testid="workspace-leaf-sources"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="workspace-leaf-work"]').exists()).toBe(true)
  })

  it("leaves its share to the columns after it, and the one before alone", () => {
    const wrapper = mountColumns()
    expect(wrapper.get('[data-testid="workspace-leaf-work"]').attributes("style")).toContain(
      "flex-grow: 80"
    )
    expect(wrapper.get('[data-testid="workspace-leaf-sources"]').attributes("style")).toContain(
      "flex-grow: 20"
    )
  })

  it("leaves it the gap and the edges that are no longer drawn as well", () => {
    // The column in front keeps the width it had down to the pixel: what the
    // row saves by drawing one card and one border less is spent where the
    // room is spent. Two cards' worth of edges: its own and the missing one's.
    const wrapper = mountColumns()
    expect(wrapper.get('[data-testid="workspace-leaf-work"]').attributes("style")).toContain(
      "calc(var(--dp-workspace-card-edges) * 2 + var(--dp-workspace-inset) * 1)"
    )
  })

  it("draws a border only between two columns that are both there", () => {
    expect(mountColumns().findAll('[data-testid="workspace-separator"]')).toHaveLength(1)
  })
})

/** A tab dragged to the edge of its column leaves the pinned one behind. */
describe("a column whose role is served by the section beside it", () => {
  const torn = () =>
    makeSplit(
      "root",
      "row",
      [
        makeLeaf("sources", ["p1"], { accepts: "sources", pinned: true }),
        makeSplit(
          "work-split",
          "column",
          [
            makeLeaf("work", [], { accepts: "work", pinned: true }),
            makeLeaf("torn", ["p2"], { accepts: "work" }),
          ],
          [50, 50]
        ),
      ],
      [30, 70]
    )

  function mountTorn() {
    const context = contextFor()
    context.tree.value = torn()
    return mount(WorkspaceNode, {
      props: { node: torn() },
      global: { plugins: [Quasar], provide: {
        [workspaceKey as symbol]: context, [panelTargetsKey as symbol]: createPanelTargets(),
      } },
    })
  }

  it("is not on the screen, and its empty view with it", () => {
    const wrapper = mountTorn()
    expect(wrapper.find('[data-testid="workspace-leaf-work"]').exists()).toBe(false)
    expect(wrapper.findAll(".hint")).toHaveLength(0)
  })

  it("leaves the section that does hold something", () => {
    expect(mountTorn().find('[data-testid="workspace-leaf-torn"]').exists()).toBe(true)
  })
})
