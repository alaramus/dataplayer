import { beforeEach, describe, expect, it, vi } from "vitest"
import { defineComponent, effectScope, h, nextTick } from "vue"
import { z } from "zod"

import { makeLeaf, makeSplit } from "./model"
import { serializeWorkspace } from "./persist"
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

describe("restoring a saved layout", () => {
  function guarded(beforeClose: (id: string) => boolean | Promise<boolean>) {
    return useWorkspace<DemoPanel>({
      storageKey: "test-workspace", panelSchema, defaults: dragging,
      kindOf: (panel) => panel.kind,
      look: (panel) => ({ title: panel.id, icon: "square", closable: panel.id !== "p1" }),
      component: () => Stub, beforeClose,
    })
  }

  it("restores saved order, sizes and collapse state independently of later changes", async () => {
    const workspace = buildDragging()
    workspace.context.toggleCollapse("left")
    workspace.context.resize("root", 1, 2, 5, 10)
    workspace.context.activate("p3")
    const tree = workspace.context.tree.value
    workspace.context.detach("p3")
    const snapshot = workspace.snapshot()
    workspace.context.close("p2")
    workspace.open({ id: "other", kind: "rows" })
    expect(await workspace.restore(snapshot)).toBe("restored")
    expect(workspace.context.tree.value).toEqual(tree)
    expect(workspace.context.detached.value).toEqual([])
    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p1", "p2", "p3"])
  })

  it("asks only departing panels and commits no partial layout when one refuses", async () => {
    const guard = vi.fn((id: string) => id !== "p5")
    const workspace = guarded(guard)
    const snapshot = workspace.snapshot()
    workspace.open({ id: "p4", kind: "rows" })
    workspace.open({ id: "p5", kind: "rows" })
    const tree = workspace.context.tree.value
    expect(await workspace.restore(snapshot)).toBe("cancelled")
    expect(workspace.context.tree.value).toBe(tree)
    expect(workspace.context.panelIds.value).toContain("p4")
    expect(workspace.context.panelIds.value).toContain("p5")
    expect(guard.mock.calls.map(([id]) => id)).toEqual(["p4", "p5"])
    guard.mockReturnValue(true)
    expect(await workspace.restore(snapshot)).toBe("restored")
    expect(workspace.context.panelIds.value).toEqual(["p1", "p2", "p3"])
  })

  it("leaves newly opened work in place when tabs change during a close question", async () => {
    let answer: (allowed: boolean) => void = () => { throw new Error("No question") }
    const workspace = guarded(() => new Promise<boolean>((resolve) => { answer = resolve }))
    const snapshot = workspace.snapshot()
    workspace.open({ id: "p4", kind: "rows" })
    const restoring = workspace.restore(snapshot)
    workspace.open({ id: "p5", kind: "rows" })
    answer(true)
    expect(await restoring).toBe("changed")
    expect(workspace.context.panelIds.value).toContain("p5")
  })

  it("refuses malformed data, incompatible roles and removal of the fixed panel", async () => {
    const guard = vi.fn(() => true)
    const workspace = guarded(guard)
    const tree = workspace.context.tree.value
    expect(await workspace.restore("broken")).toBe("invalid")
    expect(await workspace.restore(serializeWorkspace(
      makeLeaf("work", ["p2"], { accepts: "catalog" }), [{ id: "p2", kind: "rows" }]
    ))).toBe("invalid")
    expect(await workspace.restore(serializeWorkspace(
      makeLeaf("work", ["p2"], { accepts: "rows" }), [{ id: "p2", kind: "rows" }]
    ))).toBe("invalid")
    expect(workspace.context.tree.value).toBe(tree)
    expect(guard).not.toHaveBeenCalled()
  })
})

describe("a section put aside", () => {
  /** The feature names two of the three roles; the third cannot leave. */
  function named() {
    return useWorkspace<DemoPanel>({
      storageKey: "test-workspace",
      panelSchema,
      defaults: dragging,
      kindOf: (panel) => panel.kind,
      look: (panel) => ({ title: panel.id, icon: "square" }),
      component: () => Stub,
      sectionLook: (accepts) =>
        accepts === "rows" ? { title: "Data", icon: "table_chart" } : null,
    })
  }

  it("keeps everything in it, and comes back the way it was left", () => {
    const workspace = named()
    workspace.context.activate("p3")

    workspace.context.putAside("main")
    expect(leafNamed(workspace, "main").minimized).toBe(true)
    expect(leafNamed(workspace, "main").panels).toEqual(["p2", "p3"])
    expect(leafNamed(workspace, "main").activePanel).toBe("p3")

    workspace.context.bringBack("main")
    expect(leafNamed(workspace, "main").minimized).toBe(false)
    expect(leafNamed(workspace, "main").activePanel).toBe("p3")
  })

  it("is on the bar under the name of its role, with what is waiting in it", () => {
    const workspace = named()
    workspace.context.putAside("main")

    expect(workspace.context.aside.value).toEqual([
      { id: "main", title: "Data", icon: "table_chart", panels: 2 },
    ])
  })

  it("leaves the bar when it comes back", () => {
    const workspace = named()
    workspace.context.putAside("main")
    workspace.context.bringBack("main")

    expect(workspace.context.aside.value).toEqual([])
  })

  it("comes back when what is already in it is opened again", () => {
    // What a user does: the catalog of a connection is open in the column on
    // the bar, and they press that connection in the list of sources. It used
    // to activate a tab inside a column nobody could see.
    const workspace = named()
    workspace.context.putAside("main")

    workspace.open({ id: "p2", kind: "rows" })

    expect(leafNamed(workspace, "main").minimized).toBe(false)
    expect(leafNamed(workspace, "main").activePanel).toBe("p2")
    expect(workspace.context.aside.value).toEqual([])
  })

  it("comes back when something new is opened into it", () => {
    const workspace = named()
    workspace.context.putAside("main")

    workspace.open({ id: "fresh", kind: "rows" })

    expect(leafNamed(workspace, "main").minimized).toBe(false)
    expect(leafNamed(workspace, "main").activePanel).toBe("fresh")
  })

  it("leaves the bar when the last thing in it is closed", () => {
    // The column is still marked, and still off the screen; what it would
    // bring back is nothing. Opening something into it brings it back itself.
    const workspace = named()
    workspace.context.putAside("main")
    workspace.context.close("p2")
    workspace.context.close("p3")

    expect(workspace.context.aside.value).toEqual([])
  })

  it("is left off the bar while the feature has no name for its role", () => {
    // Nothing could draw a way back to it, so nothing may send it there.
    const workspace = named()
    workspace.context.putAside("left")

    expect(workspace.context.aside.value).toEqual([])
  })

  it("is remembered, the way the width of a column is", async () => {
    const workspace = named()
    workspace.context.putAside("main")
    await nextTick()

    const stored = localStorage.getItem("test-workspace")
    expect(stored).not.toBeNull()
    expect(JSON.parse(stored ?? "{}")).toMatchObject({
      tree: { children: [{}, { id: "main", minimized: true }, {}] },
    })
  })
})

describe("detached workspace panels", () => {
  it("keeps the group a panel was torn off in, and docks it back like any other", () => {
    const workspace = buildDragging()

    workspace.context.detach("p2", "pair-1")

    expect(workspace.context.detached.value.map((entry) => entry.group)).toEqual(["pair-1"])
    expect(JSON.parse(workspace.snapshot()).tree).toEqual(JSON.parse(serializeWorkspace(dragging().tree, dragging().panels)).tree)
  })

  it("removes only the layout reference and raises the existing detached panel on open", () => {
    const workspace = buildDragging()
    workspace.context.detach("p2")
    expect(leafNamed(workspace, "main").panels).toEqual(["p3"])
    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p1", "p2", "p3"])
    workspace.context.focus("main")
    workspace.open({ id: "p2", kind: "rows" })
    expect(workspace.context.focusedDetached.value).toBe("p2")
    expect(workspace.context.detached.value).toHaveLength(1)
    expect(leafNamed(workspace, "main").panels).toEqual(["p3"])

    workspace.context.dock("p2")
    expect(leafNamed(workspace, "main").panels).toEqual(["p2", "p3"])
    expect(leafNamed(workspace, "main").activePanel).toBe("p2")
    expect(workspace.context.detached.value).toEqual([])
  })

  it("persists detached panels as docked tabs without changing the running layout", async () => {
    const scope = effectScope()
    const workspace = scope.run(buildDragging)
    if (workspace === undefined) throw new Error("Missing workspace")
    workspace.context.detach("p2")
    workspace.context.detach("p3")
    await nextTick()
    expect(workspace.context.detached.value).toHaveLength(2)
    expect(workspace.context.tree.value).not.toEqual(JSON.parse(localStorage.getItem("test-workspace") ?? "{}").tree)
    scope.stop()

    const restored = buildDragging()
    expect(restored.context.detached.value).toEqual([])
    expect(restored.panels.value.map((panel) => panel.id)).toEqual(["p1", "p2", "p3"])
    expect(leavesOf(restored.context.tree.value).flatMap((leaf) => leaf.panels).sort())
      .toEqual(["p1", "p2", "p3"])
  })

  it("keeps a detached window's return destination when its panel id changes", () => {
    const workspace = buildDragging()
    workspace.context.detach("p2")
    workspace.replace("p2", { id: "saved", kind: "rows" })
    expect(workspace.context.detached.value[0]?.panelId).toBe("saved")
    expect(workspace.context.focusedDetached.value).toBe("saved")
    workspace.context.dock("saved")
    expect(leafNamed(workspace, "main").panels).toEqual(["saved", "p3"])
    expect(workspace.context.panelIds.value).not.toContain("p2")
  })

  it("keeps the fixed panel in place and never leaves the workspace without a section", () => {
    const workspace = useWorkspace<DemoPanel>({
      storageKey: "fixed-test", panelSchema, defaults: dragging,
      kindOf: (panel) => panel.kind,
      look: (panel) => ({ title: panel.id, icon: "square", closable: panel.id !== "p1" }),
      component: () => Stub,
    })
    expect(workspace.context.canDetach("p1")).toBe(false)
    workspace.context.detach("p1")
    expect(workspace.context.detached.value).toEqual([])

    const single = build()
    single.context.detach("p2")
    expect(single.context.canDetach("p1")).toBe(false)
    expect(single.context.canDetach("missing")).toBe(false)
  })

  it("asks the panel before closing its window, and removes its metadata on acceptance", async () => {
    const beforeClose = vi.fn(() => false)
    const workspace = useWorkspace<DemoPanel>({
      storageKey: "close-test", panelSchema, defaults: dragging,
      kindOf: (panel) => panel.kind, look: (panel) => ({ title: panel.id, icon: "square" }),
      component: () => Stub, beforeClose,
    })
    workspace.context.detach("p2")
    expect(beforeClose).not.toHaveBeenCalled()
    expect(await workspace.context.requestClose("p2")).toBe(false)
    expect(workspace.context.detached.value).toHaveLength(1)
    beforeClose.mockReturnValue(true)
    expect(await workspace.context.requestClose("p2")).toBe(true)
    expect(workspace.context.detached.value).toEqual([])
    expect(workspace.context.panelIds.value).not.toContain("p2")
  })

  it("clears detached panels and a pending drag on reset", () => {
    const workspace = buildDragging()
    workspace.context.detach("p2")
    beginDrag(workspace, "p3")
    workspace.reset()
    expect(workspace.context.detached.value).toEqual([])
    expect(workspace.context.dragging.value).toBeNull()
    expect(workspace.context.focusedDetached.value).toBeNull()
    expect(leafNamed(workspace, "main").panels).toEqual(["p2", "p3"])
  })
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

  it("keeps a panel that says it is not ready to go", async () => {
    const asked: string[] = []
    const workspace = useWorkspace<DemoPanel>({
      storageKey: "test-workspace",
      panelSchema,
      defaults,
      kindOf: (panel) => panel.kind,
      look: (panel) => ({ title: panel.id, icon: "square" }),
      component: () => Stub,
      beforeClose: (panelId) => {
        asked.push(panelId)
        return false
      },
    })

    await workspace.context.requestClose("p1")

    expect(asked).toEqual(["p1"])
    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p1", "p2"])
  })

  it("closes a panel that says it may go", async () => {
    const workspace = useWorkspace<DemoPanel>({
      storageKey: "test-workspace",
      panelSchema,
      defaults,
      kindOf: (panel) => panel.kind,
      look: (panel) => ({ title: panel.id, icon: "square" }),
      component: () => Stub,
      beforeClose: () => Promise.resolve(true),
    })

    await workspace.context.requestClose("p1")

    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p2"])
  })

  // Nothing asked is the same as yes, so a screen that never sets the hook
  // keeps the plain behaviour of the cross.
  it("closes a panel when nothing was asked", async () => {
    const workspace = build()
    await workspace.context.requestClose("p1")
    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p2"])
  })

  it("closes every tab of a section but the active one", async () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "rows" })
    workspace.open({ id: "p4", kind: "rows" })

    await workspace.context.closeOthers("main")

    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p1", "p4"])
  })

  it("leaves the tabs of every other section alone", async () => {
    const workspace = build()
    workspace.open({ id: "p3", kind: "rows" })

    await workspace.context.closeOthers("main")

    expect(workspace.panels.value.map((panel) => panel.id)).toContain("p1")
  })

  // The command means "the crosses of all the others", so it asks what a
  // cross would ask - and one panel keeping itself does not keep the rest.
  it("keeps a panel that says it is not ready to go when the others are closed", async () => {
    const workspace = useWorkspace<DemoPanel>({
      storageKey: "test-workspace",
      panelSchema,
      defaults,
      kindOf: (panel) => panel.kind,
      look: (panel) => ({ title: panel.id, icon: "square" }),
      component: () => Stub,
      beforeClose: (panelId) => panelId !== "p3",
    })
    workspace.open({ id: "p3", kind: "rows" })
    workspace.open({ id: "p4", kind: "rows" })

    await workspace.context.closeOthers("main")

    // p2 went, p3 kept itself, p4 is the one being looked at, and p1 is in
    // another section entirely.
    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p1", "p3", "p4"])
  })

  it("keeps a panel the feature says has no cross", async () => {
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

    await workspace.context.closeOthers("main")

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

  it("opens a copy in a section immediately right of its source", () => {
    const workspace = build()
    workspace.open({ id: "copy", kind: "catalog" }, { beside: "p1" })

    const leaves = leavesOf(workspace.context.tree.value)
    expect(leaves.map((leaf) => leaf.panels)).toEqual([["p1"], ["copy"], ["p2"]])
    expect(workspace.context.focusedLeaf.value).toBe(leaves[1]?.id)
  })

  it("moves a panel already open in the source's strip beside it rather than over it", () => {
    // The Search tab shares its strip with a catalog; opening that catalog
    // from the tab must leave the tab in sight (D205).
    const workspace = build()
    workspace.open({ id: "search", kind: "catalog" })
    workspace.context.activate("search")
    workspace.open({ id: "p1", kind: "catalog" }, { beside: "search" })

    const leaves = leavesOf(workspace.context.tree.value)
    expect(leaves.map((leaf) => leaf.panels)).toEqual([["search"], ["p1"], ["p2"]])
    expect(leaves[0]?.activePanel).toBe("search")
  })

  it("only brings forward a panel open elsewhere, whatever it is asked to stand beside", () => {
    const workspace = build()
    workspace.open({ id: "search", kind: "catalog" }, { beside: "p1" })
    const before = leavesOf(workspace.context.tree.value).map((leaf) => leaf.panels)
    workspace.open({ id: "p2", kind: "rows" }, { beside: "search" })
    expect(leavesOf(workspace.context.tree.value).map((leaf) => leaf.panels)).toEqual(before)
  })

  it("keeps the source on the tab the copy was taken from", () => {
    // The copy joins the source strip on its way beside it and becomes its
    // active tab; moving it out used to fall back to the first tab.
    const workspace = buildDragging()
    workspace.context.activate("p3")
    workspace.open({ id: "copy", kind: "rows" }, { beside: "p3" })

    const source = leavesOf(workspace.context.tree.value).find((leaf) => leaf.panels.includes("p2"))
    expect(source?.panels).toEqual(["p2", "p3"])
    expect(source?.activePanel).toBe("p3")
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

describe("the key a layout is kept under", () => {
  function keyed(storageKey: string | null) {
    return useWorkspace<DemoPanel>({
      storageKey,
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

  it("keeps nothing while there is no key, and follows the one it is given", async () => {
    const mine = defaults()
    mine.panels = [...mine.panels, { id: "p3", kind: "rows" }]
    const tree = mine.tree as SplitNode
    const main = tree.children[1] as LeafNode
    mine.tree = makeSplit("root", "row", [tree.children[0]!, { ...main, panels: ["p2", "p3"] }], [30, 70])
    localStorage.setItem("layout:me", serializeWorkspace(mine.tree, mine.panels))

    const scope = effectScope()
    const workspace = scope.run(() => keyed(null))!
    workspace.open({ id: "stranger", kind: "rows" })
    await nextTick()
    expect(localStorage.length).toBe(1)

    await workspace.follow("layout:me")
    await nextTick()
    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p1", "p2", "p3"])

    await workspace.follow("layout:new")
    await nextTick()
    expect(workspace.panels.value.map((panel) => panel.id)).toEqual(["p1", "p2"])
    expect(localStorage.getItem("layout:new")).not.toBeNull()
    scope.stop()
  })

  it("keeps a panel opened while the person was unknown", async () => {
    const scope = effectScope()
    const workspace = scope.run(() => keyed(null))!
    workspace.open({ id: "search", kind: "catalog" })
    await nextTick()
    expect(localStorage.length).toBe(0)

    await workspace.follow("layout:me")
    await nextTick()
    expect(workspace.panels.value.map((panel) => panel.id)).toContain("search")
    expect(localStorage.getItem("layout:me")).toContain("search")
    scope.stop()
  })
})
