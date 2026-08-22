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
})
