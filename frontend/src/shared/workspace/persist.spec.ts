import { describe, expect, it } from "vitest"
import { z } from "zod"

import { makeLeaf, makeSplit } from "./model"
import { parseWorkspace, serializeWorkspace, WORKSPACE_VERSION } from "./persist"

const panelSchema = z.object({ id: z.string(), kind: z.literal("demo") })
type DemoPanel = z.infer<typeof panelSchema>

const panels: DemoPanel[] = [
  { id: "p1", kind: "demo" },
  { id: "p2", kind: "demo" },
]
const tree = makeSplit("root", "row", [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2"])], [40, 60])

describe("a stored workspace", () => {
  it("comes back the way it went in", () => {
    const restored = parseWorkspace(serializeWorkspace(tree, panels), panelSchema)
    expect(restored?.tree).toEqual(tree)
    expect(restored?.panels).toEqual(panels)
  })

  it("brings back an empty pinned section with the role it accepts", () => {
    const columns = makeSplit(
      "root",
      "row",
      [
        makeLeaf("sources", ["p1"], { accepts: "sources", pinned: true }),
        makeLeaf("work", [], { accepts: "work", pinned: true }),
      ],
      [40, 60]
    )
    const restored = parseWorkspace(serializeWorkspace(columns, [panels[0]!]), panelSchema)
    expect(restored?.tree).toEqual(columns)
  })

  it("is refused when a section that is not pinned holds no panels", () => {
    const broken = makeSplit(
      "root",
      "row",
      [{ kind: "leaf", id: "a", panels: [], activePanel: null, collapsed: false }, makeLeaf("b", ["p2"])],
      [40, 60]
    )
    const raw = JSON.stringify({ version: WORKSPACE_VERSION, tree: broken, panels })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when a section holds panels but says nothing is active", () => {
    const broken = makeSplit(
      "root",
      "row",
      [{ kind: "leaf", id: "a", panels: ["p1"], activePanel: null, collapsed: false }, makeLeaf("b", ["p2"])],
      [40, 60]
    )
    const raw = JSON.stringify({ version: WORKSPACE_VERSION, tree: broken, panels })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  // The layout written before columns existed is one section holding
  // everything. Restoring it would leave the user without the two columns the
  // screen now promises, so it is refused like any other foreign version.
  it("is refused when it was written by the version before columns", () => {
    const raw = JSON.stringify({ version: 1, tree, panels })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  // A data tab now carries the connection it came from, so a layout written
  // before that would restore tabs that cannot say whose they are.
  it("is refused when it was written before a data tab named its connection", () => {
    const raw = JSON.stringify({ version: 2, tree, panels })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when there is nothing stored", () => {
    expect(parseWorkspace(null, panelSchema)).toBeNull()
  })

  it("is refused when it is not json at all", () => {
    expect(parseWorkspace("{ not json", panelSchema)).toBeNull()
  })

  it("is refused when the version is not the one we write", () => {
    const raw = JSON.stringify({ version: WORKSPACE_VERSION + 1, tree, panels })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when a panel does not match the schema of the feature", () => {
    const raw = JSON.stringify({
      version: WORKSPACE_VERSION,
      tree,
      panels: [{ id: "p1", kind: "something-else" }],
    })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when a section names a panel that was not stored", () => {
    const raw = JSON.stringify({ version: WORKSPACE_VERSION, tree, panels: [panels[0]] })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when the active panel is not in the section", () => {
    const broken = makeSplit(
      "root",
      "row",
      [{ kind: "leaf", id: "a", panels: ["p1"], activePanel: "p2", collapsed: false }, makeLeaf("b", ["p2"])],
      [40, 60]
    )
    const raw = JSON.stringify({ version: WORKSPACE_VERSION, tree: broken, panels })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when a split has a size for every child but one", () => {
    const broken = { ...tree, sizes: [100] }
    const raw = JSON.stringify({ version: WORKSPACE_VERSION, tree: broken, panels })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })

  it("is refused when the split with the wrong sizes is deep in the tree", () => {
    // The root here is sound, so this fails only if the check recurses.
    const deep = makeSplit(
      "root",
      "row",
      [
        makeLeaf("a", ["p1"]),
        makeSplit(
          "inner",
          "column",
          [makeLeaf("b", ["p2"]), makeLeaf("c", ["p3"])],
          [34, 33, 33]
        ),
      ],
      [40, 60]
    )
    const raw = JSON.stringify({
      version: WORKSPACE_VERSION,
      tree: deep,
      panels: [...panels, { id: "p3", kind: "demo" }],
    })
    expect(parseWorkspace(raw, panelSchema)).toBeNull()
  })
})
