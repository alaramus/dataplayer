import { makeLeaf, makeSplit } from "@/shared/workspace/model"
import { serializeWorkspace } from "@/shared/workspace/persist"

import type { Panel } from "../panels"

export function groupFixture(withQueries = true) {
  const panels: Panel[] = [{ id: "connectors", kind: "connectors" }]
  if (withQueries) panels.push({ id: "queries", kind: "queries" })
  // The library of queries stands in the column that navigates, not in the
  // one that holds data: `roleOf` says so, and a saved group is refused when
  // a panel sits in a column that does not accept it — which is what this
  // fixture was doing to every test that used it.
  const tree = makeSplit("root", "row", [
    makeLeaf("sources", ["connectors"], { accepts: "sources", pinned: true }),
    makeLeaf("navigate", withQueries ? ["queries"] : [], { accepts: "navigate", pinned: true }),
    makeLeaf("work", [], { accepts: "work", pinned: true }),
  ], [20, 28, 52])
  return { tree, panels, snapshot: serializeWorkspace(tree, panels) }
}
