import type { connectorsReadCatalogResponses } from "@/client"
import type { NodeRepresentation } from "@/client"

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
export type NodeRole = "group" | "container" | "leaf"

const ROLES: Record<CatalogNode["kind"], NodeRole> = {
  schema: "group",
  directory: "container",
  table: "leaf",
  view: "leaf",
  file: "leaf",
  dataset: "leaf",
  entry: "leaf",
  // A report is opened; the section holding them has children, so the rule
  // below turns that one into a place to walk into (D55).
  report: "leaf",
}

export interface ListNode {
  id: string
  label: string
  caption?: string
  icon: string
  role: NodeRole
  kind: CatalogNode["kind"]
  /**
   * Whether opening this node has any view. Decided from the representations
   * rather than the source type: a directory has none, while a file may have
   * a native content viewer, a table projection, both, or neither yet.
   */
  readable: boolean
  /** Every representation, preferred one first, exactly as the source sent it. */
  representations: NodeRepresentation[]
  describable: boolean
  /** Whether the source will say what this node is: its facts and its format (D75). */
  summarizable: boolean
  /**
   * Where this row was found, in the source's own words.
   *
   * Only a search result has one: a level says where everything on it is by
   * being that level (D76).
   */
  location?: string
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

/**
 * The icon of each kind, by its ligature name in the bundled Material Icons.
 *
 * Exported so a test can check every name against the set that actually ships:
 * a name from the newer Material Symbols is not a missing picture but a broken
 * row, because `q-icon` draws the literal word and it overflows its box.
 */
export const ICONS: Record<CatalogNode["kind"], string> = {
  schema: "folder",
  table: "table_chart",
  view: "visibility",
  directory: "folder_open",
  file: "insert_drive_file",
  dataset: "grid_on",
  entry: "insert_drive_file",
  // Names from the Material Icons set the app actually bundles. A name that is
  // only in the newer Material Symbols renders as the literal word, which
  // overflows its 18px box and covers the row's tick box — the icon is drawn
  // over the control beside it, and the row cannot be ticked.
  report: "assessment",
}

/** The section of reports, which is a report with children rather than a folder. */
export const REPORT_SECTION_ICON = "dns"

const FILE_ICONS: Partial<Record<NodeRepresentation["kind"], string>> = {
  table: "grid_on",
  text: "description",
  json: "data_object",
  jsonl: "format_list_numbered",
  image: "image",
  markdown: "article",
  audio: "graphic_eq",
  video: "movie",
  pdf: "picture_as_pdf",
  sql: "code",
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

/**
 * What the catalog does with one node.
 *
 * The kind decides it, with one exception the kind cannot express: a file that
 * says it has children is a place one walks into, because a workbook holds
 * sheets and each of them is a node of its own (D51). An empty directory is
 * still a directory, so the exception only ever adds a way in.
 */
export function roleOf(node: CatalogNode): NodeRole {
  const role = ROLES[node.kind]
  return role === "leaf" && node.has_children ? "container" : role
}

function iconOf(node: CatalogNode): string {
  if (node.kind === "report") {
    return node.has_children ? REPORT_SECTION_ICON : ICONS.report
  }
  // A file and a member of one are drawn the same way: by what opening them
  // shows, and as a folder when they are walked into instead.
  if (node.kind !== "file" && node.kind !== "entry") return ICONS[node.kind]
  const preferred = node.representations[0]
  if (preferred === undefined) {
    return node.has_children ? ICONS.directory : ICONS[node.kind]
  }
  return FILE_ICONS[preferred.kind] ?? ICONS[node.kind]
}

function captionOf(node: CatalogNode): string | undefined {
  switch (node.kind) {
    case "table":
      return node.row_count_estimate === null || node.row_count_estimate === undefined
        ? undefined
        : `~${node.row_count_estimate} rows`
    case "view":
      return node.is_materialized ? "materialized view" : "view"
    case "report":
      // The source's own line about what the report answers. Nothing here
      // rewrites it: only the source knows what its statement is for.
      return node.description ?? undefined
    case "file":
      return formatSize(node.size_bytes)
    case "dataset":
      return datasetCaption(node)
    case "entry":
      return entryCaption(node)
    default:
      return undefined
  }
}

/** What a sheet says about itself before it is opened. */
function datasetCaption(node: Extract<CatalogNode, { kind: "dataset" }>): string | undefined {
  const parts: string[] = []
  if (node.row_count !== null && node.row_count !== undefined) {
    parts.push(counted(node.row_count, "row"))
  }
  if (node.column_count !== null && node.column_count !== undefined) {
    parts.push(counted(node.column_count, "column"))
  }
  // A sheet hidden in the spreadsheet is still listed: hiding is presentation
  // rather than permission, and saying so is what keeps that honest.
  if (node.hidden === true) parts.push("hidden")
  return parts.length === 0 ? undefined : parts.join(" · ")
}

/** What an entry of an archive says about itself before it is opened. */
function entryCaption(node: Extract<CatalogNode, { kind: "entry" }>): string | undefined {
  if (node.is_link === true) return "link"
  if (node.is_encrypted === true) return "encrypted"
  if (node.has_children) return undefined
  return node.size_bytes === null || node.size_bytes === undefined
    ? undefined
    : formatSize(node.size_bytes)
}

function counted(count: number, noun: string): string {
  return `${String(count)} ${noun}${count === 1 ? "" : "s"}`
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

export function isReadableNode(node: CatalogNode): boolean {
  // Kept as the rows-specific question used by the import dialog. Opening a
  // catalog node uses the preferred representation instead.
  return node.representations.some((representation) => representation.kind === "table")
}

/**
 * Map catalog nodes onto rows of the list.
 *
 * The switches narrow on `kind`, so a new node kind added on the backend
 * becomes a type error here rather than a silently missing caption or a row
 * nobody decided what to do with.
 */
export function toListNodes(nodes: CatalogNode[], group?: string): ListNode[] {
  return nodes.map((node) => ({
    id: node.id,
    label: node.name,
    caption: captionOf(node),
    icon: iconOf(node),
    role: roleOf(node),
    kind: node.kind,
    readable: node.representations.length > 0,
    representations: node.representations,
    system: isSystem(node),
    describable: node.describable === true,
    summarizable: node.summarizable === true,
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
