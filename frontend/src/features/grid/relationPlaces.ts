import { toListNodes } from "@/features/catalog/nodes"
import type { CatalogNode } from "@/features/catalog/nodes"

/**
 * What the destination calls the thing being made.
 *
 * Read off the kind of the node that was picked, never off the type of the
 * source: a schema takes a table and a folder takes a file, and the catalog
 * already says which of the two a node is (D45).
 */
export type Destination = "schema" | "folder"

export interface Place {
  label: string
  value: string
  kind: Destination
}

/**
 * Where a new relation could go in one connection, from its top level.
 *
 * The catalog's own rule about what a node is: a grouping is a place things
 * are kept in — a schema, a database — and a source that offers none keeps
 * them in its folders, the top one included. Nothing here takes an id apart
 * or asks what type of source this is (D21).
 */
export function placesIn(nodes: CatalogNode[], topLabel: string): Place[] {
  const rows = toListNodes(nodes)
  const groups = rows.filter((node) => node.role === "group" && !node.system)
  if (groups.length > 0) {
    return groups.map((node) => ({
      label: node.label,
      value: node.id,
      kind: "schema" as const,
    }))
  }
  // A directory, and not merely something one walks into: a workbook and an
  // archive have children too, and neither can be written a file into.
  const folders = rows
    .filter((node) => node.kind === "directory")
    .map((node) => ({ label: node.label, value: node.id, kind: "folder" as const }))
  // The top level itself, named by the connection: it is where a source that
  // keeps files keeps them, and the empty id is what the source calls it.
  return [{ label: topLabel, value: "", kind: "folder" as const }, ...folders]
}
