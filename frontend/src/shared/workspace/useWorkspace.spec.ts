import { beforeEach, describe, expect, it } from "vitest"
import { defineComponent, h, nextTick } from "vue"
import { z } from "zod"

import { makeLeaf, makeSplit } from "./model"
import type { LeafNode, SplitNode } from "./model"
import { useWorkspace } from "./useWorkspace"

const panelSchema = z.object({ id: z.string(), kind: z.string() })
type DemoPanel = z.infer<typeof panelSchema>

const Stub = defineComponent({ setup: () => () => h("div") })

const defaults = () => ({
  tree: makeSplit("root", "row", [makeLeaf("left", ["p1"]), makeLeaf("main", ["p2"])], [30, 70]),
  panels: [
    { id: "p1", kind: "catalog" },
    { id: "p2", kind: "rows" },
  ] as DemoPanel[],
})

function build() {
  return useWorkspace<DemoPanel>({
    storageKey: "test-workspace",
    panelSchema,
    defaults,
    kindOf: (panel) => panel.kind,
    look: (panel) => ({ title: panel.id, icon: "square" }),
    component: () => Stub,
  })
}

beforeEach(() => {
  localStorage.clear()
})

describe("a workspace", () => {
  it("starts from the defaults when nothing is stored", () => {
    expect(build().context.tree.value.id).toBe("root")
  })

  it("opens a new panel beside one of the same kind", () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "rows" })
    const main = (workspace.context.tree.value as SplitNode).children[1] as LeafNode
    expect(main.panels).toEqual(["p2", "p3"])
    expect(main.activePanel).toBe("p3")
  })

  it("activates a panel that is already open instead of opening it twice", () => {
    const workspace = build()
    workspace.open({ id: "p1", kind: "catalog" })
    expect(workspace.panels.value).toHaveLength(2)
  })

  it("forgets a panel when it is closed", () => {
    const workspace = build()
    workspace.context.close("p1")
    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p2"])
    expect(workspace.context.tree.value.id).toBe("main")
  })

  it("keeps the last panel rather than leaving an empty workspace", () => {
    const workspace = build()
    workspace.context.close("p1")
    workspace.context.close("p2")
    expect(workspace.panels.value).toHaveLength(1)
  })

  it("writes what it has to storage and reads it back", async () => {
    const first = build()
    first.open({ id: "p3", kind: "rows" })
    // The watcher persists on the next tick, so several changes in one tick
    // cost one write rather than one each. The test waits; the drag does not.
    await nextTick()
    const second = build()
    expect(second.panels.value.map((panel) => panel.id)).toEqual(["p1", "p2", "p3"])
  })

  it("falls back to the defaults when storage holds nonsense", () => {
    localStorage.setItem("test-workspace", "{ not json")
    expect(build().panels.value).toHaveLength(2)
  })

  it("returns to the defaults on reset, and stores them", async () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "rows" })
    await nextTick()
    workspace.reset()
    await nextTick()
    expect(workspace.panels.value).toHaveLength(2)
    // What is stored is the default layout now, not the one we left behind.
    expect(build().panels.value).toHaveLength(2)
  })

  it("moves a panel where a drag ends", () => {
    const workspace = build()
    workspace.context.startDrag("p1")
    workspace.context.endDrag("main", "center")
    expect(workspace.context.tree.value.kind).toBe("leaf")
    expect((workspace.context.tree.value as LeafNode).panels).toEqual(["p2", "p1"])
  })

  it("leaves the layout alone when a drag ends nowhere", () => {
    const workspace = build()
    const before = workspace.context.tree.value
    workspace.context.startDrag("p1")
    workspace.context.endDrag(null, null)
    expect(workspace.context.tree.value).toBe(before)
    expect(workspace.context.dragging.value).toBeNull()
  })
})
