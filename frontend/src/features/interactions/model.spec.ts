import { describe, expect, it } from "vitest"

import type { InteractionMap } from "@/client"
import { graphProblem } from "@/shared/graph/model"
import { endsOf, mapGraph } from "./model"

const answer: InteractionMap = {
  connections: [
    {
      id: "db", name: "Sales", adapter_type: "postgres", type_title: "PostgreSQL",
      category: "sql", category_title: "SQL Databases", access: "read",
    },
    {
      id: "files", name: "Files", adapter_type: "file", type_title: "Personal storage",
      category: "files", category_title: "Files & Storage", access: "own",
    },
  ],
  arrows: [
    {
      source_connector_id: "db",
      destination_connector_id: "files",
      operations: [{ kind: "relation_csv", title: "Save as CSV", mode: "copy", available: true }],
    },
    {
      source_connector_id: "files",
      destination_connector_id: "db",
      operations: [
        {
          kind: "rows_new_relation", title: "Create a table", mode: "copy", available: false,
          reason: "Needs structure access to Sales",
        },
        {
          kind: "rows_into_relation", title: "Add rows to a table", mode: "copy", available: false,
          reason: "Needs write access to Sales",
        },
      ],
    },
  ],
}

describe("the map of what connections give each other", () => {
  it("draws a node per connection, grouped by what kind of source it is", () => {
    const graph = mapGraph(answer)

    expect(graphProblem(graph)).toBeNull()
    expect(graph.nodes.map((node) => [node.id, node.label, node.caption, node.groupId])).toEqual([
      ["db", "Sales", "PostgreSQL", "sql"],
      ["files", "Files", "Personal storage", "files"],
    ])
    expect(graph.nodes[0]?.details).toContainEqual({ label: "Your access", value: "Read" })
    expect(graph.groups).toEqual([
      { id: "sql", label: "SQL Databases" },
      { id: "files", label: "Files & Storage" },
    ])
  })

  it("draws one arrow a direction, named by what it does, dashed when none of it is open", () => {
    const [out, into] = mapGraph(answer).edges

    expect(out).toMatchObject({
      source: { nodeId: "db" }, target: { nodeId: "files" },
      label: "Save as CSV", directed: true, dashed: false,
    })
    expect(into?.label).toBe("Create a table · Add rows to a table")
    expect(into?.dashed).toBe(true)
    expect(into?.details).toEqual([
      { label: "Create a table", value: "Needs structure access to Sales" },
      { label: "Add rows to a table", value: "Needs write access to Sales" },
    ])
    expect(out?.details).toEqual([{ label: "Save as CSV", value: "Open to you" }])
  })

  it("names the two ends of an arrow for the pair it opens", () => {
    const [out] = mapGraph(answer).edges

    expect(endsOf(answer, out!.id)).toEqual({ source: "db", destination: "files" })
    expect(endsOf(answer, "nothing")).toBeNull()
  })
})
