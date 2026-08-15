import type { connectorsReadCatalogResponses } from "@/client"

/** One catalog node as the API returns it: a union discriminated by `kind`. */
export type CatalogNode = connectorsReadCatalogResponses[200][number]

export interface TreeNode {
  id: string
  label: string
  caption?: string
  icon: string
  lazy: boolean
}

const ICONS: Record<CatalogNode["kind"], string> = {
  schema: "folder",
  table: "table_chart",
  view: "visibility",
  column: "label",
}

function captionOf(node: CatalogNode): string | undefined {
  switch (node.kind) {
    case "column":
      return node.nullable ? `${node.data_type}, nullable` : node.data_type
    case "table":
      return node.row_count_estimate === null || node.row_count_estimate === undefined
        ? undefined
        : `~${node.row_count_estimate} rows`
    case "view":
      return node.is_materialized ? "materialized view" : "view"
    default:
      return undefined
  }
}

/**
 * Map catalog nodes onto what QTree expects.
 *
 * The switch narrows on `kind`, so a new node kind added on the backend
 * becomes a type error here rather than a silently missing caption.
 */
export function toTreeNodes(nodes: CatalogNode[]): TreeNode[] {
  return nodes.map((node) => ({
    id: node.id,
    label: node.name,
    caption: captionOf(node),
    icon: ICONS[node.kind],
    lazy: node.has_children,
  }))
}
