import { makeLeaf, makeSplit } from "@/shared/workspace/model"
import { serializeWorkspace } from "@/shared/workspace/persist"

import type { Panel } from "../panels"

export function groupFixture(withQueries = true) {
  const panels: Panel[] = [{ id: "connectors", kind: "connectors" }]
  if (withQueries) panels.push({ id: "queries", kind: "queries" })
  const tree = makeSplit("root", "row", [
    makeLeaf("sources", ["connectors"], { accepts: "sources", pinned: true }),
    makeLeaf("navigate", [], { accepts: "navigate", pinned: true }),
    makeLeaf("work", withQueries ? ["queries"] : [], { accepts: "work", pinned: true }),
  ], [20, 28, 52])
  return { tree, panels, snapshot: serializeWorkspace(tree, panels) }
}
