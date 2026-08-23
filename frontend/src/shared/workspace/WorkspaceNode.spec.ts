import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"
import { defineComponent, h, ref } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { makeLeaf, makeSplit } from "./model"
import WorkspaceNode from "./WorkspaceNode.vue"

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
    focusedLeaf: ref(null),
    dragging: ref(null),
    lookOf: (panelId) => ({ title: `title ${panelId}`, icon: "square" }),
    componentOf: () => Stub,
    // The middle column has no empty view of its own: a column appears with
    // what goes in it. See P5.
    emptyOf: (accepts) => (accepts === "work" ? Hint : null),
    admissionOf: () => ({ accepts: true, remaining: 1 }),
    collapsedOf: () => null,
    activate: () => undefined,
    close: () => undefined,
    closeOthers: () => undefined,
    focus: () => undefined,
    toggleCollapse: () => undefined,
    resize: () => undefined,
    startDrag: () => undefined,
    endDrag: () => undefined,
  }
}

function mountColumns() {
  return mount(WorkspaceNode, {
    props: { node: columns() },
    global: { plugins: [Quasar], provide: { [workspaceKey as symbol]: contextFor() } },
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

  it("gives its share to the next column along", () => {
    const wrapper = mountColumns()
    expect(wrapper.get('[data-testid="workspace-leaf-work"]').attributes("style")).toContain(
      "flex: 80"
    )
    expect(wrapper.get('[data-testid="workspace-leaf-sources"]').attributes("style")).toContain(
      "flex: 20"
    )
  })

  it("draws a border only between two columns that are both there", () => {
    expect(mountColumns().findAll('[data-testid="workspace-separator"]')).toHaveLength(1)
  })
})
