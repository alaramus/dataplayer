import type { connectorsReadCatalogResponses } from "@/client"

/** One catalog node as the API returns it: a union discriminated by `kind`. */
export type CatalogNode = connectorsReadCatalogResponses[200][number]

/**
 * What the catalog does with a node, decided by its kind.
 *
 * This table is the whole reason the screen never asks what type of source it
 * is looking at. A schema is a grouping rather than a place — it belongs in
 * the filter above the list, not in the list — while a directory is a place
 * one walks into, and a table is something to open. Adding a source type that
 * brings databases or namespaces means adding a line here, not a branch.
 */
export type NodeRole = "group" | "container" | "leaf" | "hidden"

const ROLES: Record<CatalogNode["kind"], NodeRole> = {
  schema: "group",
  directory: "container",
  table: "leaf",
  view: "leaf",
  file: "leaf",
  // A column belongs to the grid that shows the rows, and is not a level of
  // the catalog: a click on a table would otherwise have two meanings.
  column: "hidden",
}

export interface ListNode {
  id: string
  label: string
  caption?: string
  icon: string
  role: NodeRole
  kind: CatalogNode["kind"]
  /**
   * Whether opening this node shows rows. Decided here rather than in a
   * component: a table and a view have rows, a directory does not, and a file
   * has them only when something can read it.
   */
  readable: boolean
  rowEstimate?: number | null
  /**
   * Whether the source considers this part of its own machinery. Only used to
   * decide what is selected before the user has chosen anything: `pg_catalog`
   * is a real schema, and hiding it would be deciding for the user.
   */
  system: boolean
  /** Which grouping this node came from, when several were listed at once. */
  group?: string
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

export function roleOfKind(kind: CatalogNode["kind"]): NodeRole {
  return ROLES[kind]
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

function isSystem(node: CatalogNode): boolean {
  switch (node.kind) {
    case "schema":
    case "table":
    case "view":
      return node.is_system ?? false
    default:
      return false
  }
}

function isReadable(node: CatalogNode): boolean {
  switch (node.kind) {
    case "table":
    case "view":
      return true
    case "file":
      // A picture or an archive stays visible in the list, but opening it
      // would only produce an error the user did not ask for.
      return node.content_kind !== "opaque"
    default:
      return false
  }
}

/**
 * Map catalog nodes onto rows of the list.
 *
 * The switches narrow on `kind`, so a new node kind added on the backend
 * becomes a type error here rather than a silently missing caption or a row
 * nobody decided what to do with. Nodes of a hidden kind are dropped.
 */
export function toListNodes(nodes: CatalogNode[], group?: string): ListNode[] {
  return nodes
    .filter((node) => roleOfKind(node.kind) !== "hidden")
    .map((node) => ({
      id: node.id,
      label: node.name,
      caption: captionOf(node),
      icon: iconOf(node),
      role: roleOfKind(node.kind),
      kind: node.kind,
      readable: isReadable(node),
      system: isSystem(node),
      // Only a table knows roughly how many rows it holds. A file would have
      // to be read from end to end to answer, so the grid pages without a
      // total.
      rowEstimate: node.kind === "table" ? node.row_count_estimate : null,
      ...(group === undefined ? {} : { group }),
    }))
}

/** The groupings among a level's children: what the filter above it offers. */
export function groupsOf(nodes: ListNode[]): ListNode[] {
  return nodes.filter((node) => node.role === "group")
}

/**
 * Whether the head of a level says where we are.
 *
 * Read off what the level holds and never off the type of the source, which
 * is the same rule the rest of this file follows. A level that offers
 * groupings already says one thing about itself on that line, and a path of
 * one step beside it would say nothing; a level that offers none has the line
 * to itself, and drawing the path only after the first step would make it
 * appear and disappear while walking in and out.
 */
export function showsPath(depth: number, groups: ListNode[]): boolean {
  return depth > 1 || groups.length === 0
}
