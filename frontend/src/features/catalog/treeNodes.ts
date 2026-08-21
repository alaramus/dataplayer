import type { connectorsReadCatalogResponses } from "@/client"

/** One catalog node as the API returns it: a union discriminated by `kind`. */
export type CatalogNode = connectorsReadCatalogResponses[200][number]

export interface TreeNode {
  id: string
  label: string
  caption?: string
  icon: string
  lazy: boolean
  /** Kept so the dialog can tell which nodes have rows to show. */
  kind: CatalogNode["kind"]
  /**
   * Whether selecting this node shows rows. Decided here rather than in the
   * dialog: a table and a view have rows, a directory does not, and a file
   * has them only when something can read it.
   */
  readable: boolean
  rowEstimate?: number | null
}

const ICONS: Record<CatalogNode["kind"], string> = {
  schema: "folder",
  table: "table_chart",
  view: "visibility",
  column: "label",
  directory: "folder_open",
  file: "insert_drive_file",
}

const FILE_ICONS: Record<string, string> = {
  table: "grid_on",
  text: "description",
  opaque: "insert_drive_file",
}

const UNITS = ["B", "KB", "MB", "GB", "TB"]

/** File size in the shortest form that still says which unit it is. */
export function formatSize(bytes: number): string {
  let size = bytes
  let unit = 0
  while (size >= 1024 && unit < UNITS.length - 1) {
    size /= 1024
    unit += 1
  }
  const rounded = unit === 0 ? String(size) : size.toFixed(1)
  return `${rounded} ${UNITS[unit]}`
}

function iconOf(node: CatalogNode): string {
  return node.kind === "file" ? (FILE_ICONS[node.content_kind] ?? ICONS.file) : ICONS[node.kind]
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
    case "file":
      return formatSize(node.size_bytes)
    default:
      return undefined
  }
}

function isReadable(node: CatalogNode): boolean {
  switch (node.kind) {
    case "table":
    case "view":
      return true
    case "file":
      // A picture or an archive stays visible in the tree, but opening it
      // would only produce an error the user did not ask for.
      return node.content_kind !== "opaque"
    default:
      return false
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
    icon: iconOf(node),
    lazy: node.has_children,
    kind: node.kind,
    readable: isReadable(node),
    // Only a table knows roughly how many rows it holds. A file would have to
    // be read from end to end to answer, so the grid pages without a total.
    rowEstimate: node.kind === "table" ? node.row_count_estimate : null,
  }))
}
