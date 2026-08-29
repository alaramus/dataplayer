import { beforeEach, describe, expect, it } from "vitest"
import { defineComponent, h, nextTick } from "vue"
import { z } from "zod"

import { makeLeaf, makeSplit } from "./model"
import { leavesOf } from "./tree"
import type { LeafNode, SplitNode } from "./model"
import { useWorkspace } from "./useWorkspace"

const panelSchema = z.object({ id: z.string(), kind: z.string() })
type DemoPanel = z.infer<typeof panelSchema>

const Stub = defineComponent({ setup: () => () => h("div") })

const defaults = () => ({
  tree: makeSplit(
    "root",
    "row",
    [
      makeLeaf("left", ["p1"], { accepts: "catalog" }),
      makeLeaf("main", ["p2"], { accepts: "rows" }),
    ],
    [30, 70]
  ),
  panels: [
    { id: "p1", kind: "catalog" },
    { id: "p2", kind: "rows" },
  ] as DemoPanel[],
})

/** Two sections of one role and one of another: what a drop is judged by. */
const dragging = () => ({
  tree: makeSplit(
    "root",
    "row",
    [
      makeLeaf("left", ["p1"], { accepts: "catalog" }),
      makeLeaf("main", ["p2", "p3"], { accepts: "rows" }),
      makeLeaf("aside", [], { accepts: "rows", pinned: true }),
    ],
    [30, 40, 30]
  ),
  panels: [
    { id: "p1", kind: "catalog" },
    { id: "p2", kind: "rows" },
    { id: "p3", kind: "rows" },
  ] as DemoPanel[],
})

function buildDragging() {
  return useWorkspace<DemoPanel>({
    storageKey: "test-workspace",
    panelSchema,
    defaults: dragging,
    kindOf: (panel) => panel.kind,
    look: (panel) => ({ title: panel.id, icon: "square" }),
    component: () => Stub,
  })
}

/** Press a tab and move far enough that the press became a drag. */
function beginDrag(workspace: ReturnType<typeof buildDragging>, panelId: string) {
  workspace.context.press(panelId, 100, 100)
  workspace.context.pointerMoved(140, 100)
}

function leafNamed(workspace: ReturnType<typeof buildDragging>, id: string): LeafNode {
  const found = leavesOf(workspace.context.tree.value).find((leaf) => leaf.id === id)
  if (found === undefined) throw new Error(`no section ${id}`)
  return found
}

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

  it("replaces a panel identity without moving its tab", () => {
    const workspace = build()

    workspace.replace("p2", { id: "renamed", kind: "rows" })

    const main = (workspace.context.tree.value as SplitNode).children[1] as LeafNode
    expect(main.panels).toEqual(["renamed"])
    expect(main.activePanel).toBe("renamed")
    expect(workspace.panels.value).toContainEqual({ id: "renamed", kind: "rows" })
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

  it("closes every tab of a section but the active one", () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "rows" })
    workspace.open({ id: "p4", kind: "rows" })

    workspace.context.closeOthers("main")

    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p1", "p4"])
  })

  it("leaves the tabs of every other section alone", () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "rows" })

    workspace.context.closeOthers("main")

    expect(workspace.panels.value.map((panel) => panel.id)).toContain("p1")
  })

  it("keeps a panel the feature says has no cross", () => {
    /* The command means "the crosses of all the others", and a panel with no
       cross of its own has none to press. */
    const workspace = useWorkspace<DemoPanel>({
      storageKey: "test-workspace",
      panelSchema,
      defaults: () => ({
        tree: makeSplit("root", "row", [makeLeaf("left", ["p1"]), makeLeaf("main", ["p2"])], [30, 70]),
        panels: [
          { id: "p1", kind: "catalog" },
          { id: "p2", kind: "rows" },
        ] as DemoPanel[],
      }),
      kindOf: (panel) => panel.kind,
      look: (panel) => ({ title: panel.id, icon: "square", closable: panel.id !== "p2" }),
      component: () => Stub,
    })
    workspace.open({ id: "p3", kind: "rows" })

    workspace.context.closeOthers("main")

    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p1", "p2", "p3"])
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

  it("stores the defaults on reset, rather than leaving what was there", async () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "rows" })
    await nextTick()
    // Storage now names three panels. Without this line the test could not
    // tell a reset that wrote the defaults from a workspace that never wrote
    // anything: an empty key falls back to those same defaults.
    expect(build().panels.value).toHaveLength(3)

    workspace.reset()
    await nextTick()
    expect(workspace.panels.value).toHaveLength(2)
    expect(build().panels.value.map((panel) => panel.id)).toEqual(["p1", "p2"])
  })

  it("moves a panel where a drag ends", () => {
    const workspace = buildDragging()
    beginDrag(workspace, "p3")
    workspace.context.endDrag("aside", "center")
    expect(leafNamed(workspace, "aside").panels).toEqual(["p3"])
    expect(leafNamed(workspace, "main").panels).toEqual(["p2"])
  })

  it("does not begin a drag until the pointer has actually moved", () => {
    // A tab now leaves its strip the moment a drag begins, so a press that
    // never became one would make it blink on every click. See G1.
    const workspace = buildDragging()
    workspace.context.press("p3", 100, 100)
    expect(workspace.context.dragging.value).toBeNull()
    workspace.context.pointerMoved(101, 101)
    expect(workspace.context.dragging.value).toBeNull()
    workspace.context.pointerMoved(106, 100)
    expect(workspace.context.dragging.value).toBe("p3")
  })

  it("forgets a press that ended without a drag", () => {
    const workspace = buildDragging()
    workspace.context.press("p3", 100, 100)
    workspace.context.endDrag(null, null)
    workspace.context.pointerMoved(200, 200)
    expect(workspace.context.dragging.value).toBeNull()
  })

  it("refuses a panel a section does not take", () => {
    // The three columns are a property of the screen: a grid dropped into the
    // column of connections would break them with no way back. See P1.
    const workspace = buildDragging()
    const before = workspace.context.tree.value
    beginDrag(workspace, "p3")
    workspace.context.endDrag("left", "center")
    expect(workspace.context.tree.value).toBe(before)
  })

  it("says of a section whether it takes what is being dragged", () => {
    const workspace = buildDragging()
    beginDrag(workspace, "p3")
    expect(workspace.context.admissionOf("main").accepts).toBe(true)
    expect(workspace.context.admissionOf("left").accepts).toBe(false)
  })

  it("counts what a section would keep once the dragged panel has left it", () => {
    const workspace = buildDragging()
    beginDrag(workspace, "p3")
    expect(workspace.context.admissionOf("main").remaining).toBe(1)
    expect(workspace.context.admissionOf("aside").remaining).toBe(0)
  })

  it("takes a side that would leave the target empty as a tab instead", () => {
    const workspace = buildDragging()
    beginDrag(workspace, "p3")
    workspace.context.endDrag("aside", "left")
    expect(leavesOf(workspace.context.tree.value).map((leaf) => leaf.id)).toEqual([
      "left",
      "main",
      "aside",
    ])
    expect(leafNamed(workspace, "aside").panels).toEqual(["p3"])
  })

  it("splits when the target would still hold something", () => {
    const workspace = buildDragging()
    beginDrag(workspace, "p3")
    workspace.context.endDrag("main", "bottom")
    expect(leavesOf(workspace.context.tree.value)).toHaveLength(4)
  })

  it("closes the panel of the same kind when the new one replaces it", () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "catalog" }, { replace: true })
    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p2", "p3"])
  })

  it("leaves panels of other kinds where they are when replacing", () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "catalog" }, { replace: true })
    expect(workspace.panels.value.some((panel) => panel.id === "p2")).toBe(true)
  })

  it("leaves the layout alone when a drag ends nowhere", () => {
    const workspace = build()
    const before = workspace.context.tree.value
    workspace.context.press("p1", 0, 0)
    workspace.context.pointerMoved(40, 0)
    workspace.context.endDrag(null, null)
    expect(workspace.context.tree.value).toBe(before)
    expect(workspace.context.dragging.value).toBeNull()
  })
})
