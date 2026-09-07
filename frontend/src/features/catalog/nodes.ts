import type { connectorsReadCatalogResponses } from "@/client"
import type { DetectedFramework, FetchColumn, NodeRepresentation } from "@/client"

/** One catalog node as the API returns it: a union discriminated by `kind`. */
export type CatalogNode = connectorsReadCatalogResponses[200][number]

/**
 * A node somebody chose somewhere else, with the connection it lives in.
 *
 * The connection travels with it because whatever was picked has to be opened,
 * read or stored against a source that is not the one the screen is standing
 * in — bringing rows in (D43), drawing a reference (D106).
 */
export interface PickedNode {
  connectorId: string
  connectorName: string
  adapterType: string
  node: CatalogNode
  /** What the source calls its columns, read as one page of it. */
  columns: FetchColumn[]
}

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
  // A key-value database is a grouping for the same reason a schema is: the
  // one named by the connection says where to start, and the others are
  // beside it in the same control rather than one folder down (D91).
  database: "group",
  directory: "container",
  table: "leaf",
  view: "leaf",
  file: "leaf",
  dataset: "leaf",
  entry: "leaf",
  // A report is opened; the section holding them has children, so the rule
  // below turns that one into a place to walk into (D55).
  report: "leaf",
  // A key is opened and read as whatever it holds. The namespace above it is
  // a directory, because that is what a namespace is.
  key: "leaf",
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
  /**
   * Why the caption says nothing was counted, where it says so.
   *
   * "N/A" is one word for two different facts, and the column has room for
   * neither of them: a table nobody has analysed has a count the server would
   * give if it were asked to look, and a view has no stored rows to count at
   * all. The word is the same on both rows; this says which one it is.
   */
  captionHint?: string
  rowEstimate?: number | null
  /**
   * Whether the source considers this part of its own machinery. Only used to
   * decide what is selected before the user has chosen anything: `pg_catalog`
   * is a real schema, and hiding it would be deciding for the user.
   */
  system: boolean
  /**
   * Whether the source says this is the grouping to open on.
   *
   * Only a grouping has one, and only where the source knows: a Redis
   * connection names the database it was written with, and opening on
   * whichever happens to be listed first would ignore what the user chose.
   */
  preferred: boolean
  /** Framework hints supplied by a schema, independent of its filtered rows. */
  frameworks?: DetectedFramework[]
  /** Which grouping this node came from, when several were listed at once. */
  group?: string
  /**
   * Whether this node holds nodes of its own as well as opening.
   *
   * A workbook does both: it opens as its first sheet, and the rest of them
   * are inside it. What opens it needs to know, so the tab it makes can offer
   * the others (D51).
   */
  holdsNodes: boolean
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
  database: "storage",
  key: "vpn_key",
}

/** The section of reports, which is a report with children rather than a folder. */
export const REPORT_SECTION_ICON = "dns"

/**
 * A view whose rows are stored, drawn as the table it keeps rather than as the
 * window it is.
 *
 * The kind of a node is what its icon says, and every other kind says it that
 * way and only that way. A word beside the eye was the one row in a catalog
 * that named itself twice.
 */
export const MATERIALIZED_VIEW_ICON = "backup_table"

/**
 * What a source's groupings are called, above the control that picks them.
 *
 * A table rather than a question about the type of the source: "Schemas" over
 * a list of Redis databases would be the old application's habit of giving one
 * word two meanings, and the kind of the node already says which word it is.
 */
const GROUP_TITLES: Partial<Record<CatalogNode["kind"], string>> = {
  schema: "Schemas",
  database: "Databases",
}

/** The word for the groupings on a level, or none when it offers no kind. */
export function groupTitle(groups: ListNode[]): string {
  const kind = groups[0]?.kind
  return (kind === undefined ? undefined : GROUP_TITLES[kind]) ?? "Groups"
}

/**
 * How each representation is drawn, wherever it is drawn.
 *
 * One table rather than one per screen. The catalog draws a node by what
 * opening it shows, and the tab that opening it produced has to agree — a
 * `.csv` drawn as a grid in the list and as a folder in its own tab is the
 * same node saying two different things about itself.
 */
export const REPRESENTATION_ICONS: Record<NodeRepresentation["kind"], string> = {
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

/**
 * What stands in the counted column of a relation nothing was counted for.
 *
 * Said rather than left blank. A column filled on some rows and empty on
 * others reads as a column somebody forgot to fill, and the reader cannot tell
 * "no rows" from "no answer" — which is the one thing an estimate must never
 * be confused with.
 */
const NOT_COUNTED = "N/A"

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
 * What the catalog does with one node. The kind decides, with one exception it
 * cannot express: a file that says it has children is walked into, because an
 * archive holds files (D53) — unless it also says how it opens, and then that
 * wins, or a workbook would be a spreadsheet behind a filing cabinet.
 */
export function roleOf(node: CatalogNode): NodeRole {
  const role = ROLES[node.kind]
  if (role !== "leaf" || !node.has_children) return role
  return node.representations.length > 0 ? "leaf" : "container"
}

function iconOf(node: CatalogNode): string {
  if (node.kind === "report") {
    return node.has_children ? REPORT_SECTION_ICON : ICONS.report
  }
  if (node.kind === "view") {
    return node.is_materialized === true ? MATERIALIZED_VIEW_ICON : ICONS.view
  }
  // A file and a member of one are drawn the same way: by what opening them
  // shows, and as a folder when they are walked into instead.
  if (node.kind !== "file" && node.kind !== "entry") return ICONS[node.kind]
  const preferred = node.representations[0]
  if (preferred === undefined) {
    return node.has_children ? ICONS.directory : ICONS[node.kind]
  }
  return REPRESENTATION_ICONS[preferred.kind] ?? ICONS[node.kind]
}

function captionOf(node: CatalogNode): string | undefined {
  switch (node.kind) {
    case "table":
      return node.row_count_estimate === null || node.row_count_estimate === undefined
        ? NOT_COUNTED
        : `~${node.row_count_estimate} rows`
    // In the same column as a table's estimate, because it is the same
    // question asked of the same kind of thing. The answer is that there is
    // nothing stored to count.
    case "view":
      return NOT_COUNTED
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
    case "key":
      return keyCaption(node)
    case "database":
      // Said even when it is nothing: a database with no keys in it is a fact
      // about the server, and an empty caption reads as one nobody counted.
      return node.keys === null || node.keys === undefined
        ? undefined
        : node.keys === 0
          ? "empty"
          : counted(node.keys, "key")
    default:
      return undefined
  }
}

/**
 * Why a relation's count is missing, for the reader who wonders.
 *
 * Only a relation has one: every other kind either states its measure or is
 * not measured at all, and a hint on a row whose column is filled would be a
 * tooltip about nothing.
 */
function captionHintOf(node: CatalogNode): string | undefined {
  if (node.kind === "view") {
    return "A view stores no rows; how many it returns is known only when it runs"
  }
  if (node.kind !== "table") return undefined
  if (node.row_count_estimate !== null && node.row_count_estimate !== undefined) {
    return undefined
  }
  return "Not analysed yet, so the server offers no estimate"
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

/**
 * What one of a key holds is called, which is not the same word for each.
 *
 * "11 items" about a string of eleven characters is a number with the wrong
 * noun on it, and the noun is the part that says what was counted.
 */
const KEY_UNITS: Partial<Record<string, string>> = {
  string: "character",
  hash: "field",
  list: "item",
  set: "member",
  zset: "member",
  stream: "entry",
}

/**
 * What a key says about itself before it is opened.
 *
 * Its type, how much is in it, and how long it has left. The expiry was read
 * when the level was listed and is already out of date by the time it is
 * drawn, which is why it is a caption and never something a decision is made
 * from.
 */
function keyCaption(node: Extract<CatalogNode, { kind: "key" }>): string | undefined {
  const parts: string[] = [node.data_type]
  if (node.length !== null && node.length !== undefined) {
    parts.push(counted(node.length, KEY_UNITS[node.data_type] ?? "item"))
  }
  if (node.ttl_seconds !== null && node.ttl_seconds !== undefined) {
    parts.push(`expires in ${formatDuration(node.ttl_seconds)}`)
  }
  return parts.join(" · ")
}

/** A number of seconds in the largest unit that still says something. */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${String(seconds)}s`
  if (seconds < 3600) return `${String(Math.round(seconds / 60))}m`
  if (seconds < 86400) return `${String(Math.round(seconds / 3600))}h`
  return `${String(Math.round(seconds / 86400))}d`
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

function isPreferred(node: CatalogNode): boolean {
  return node.kind === "database" && node.preferred === true
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
  return nodes.map((node) => {
    const hint = captionHintOf(node)
    return {
      id: node.id,
      label: node.name,
      caption: captionOf(node),
      ...(hint === undefined ? {} : { captionHint: hint }),
      icon: iconOf(node),
      role: roleOf(node),
      kind: node.kind,
      readable: node.representations.length > 0,
      representations: node.representations,
      system: isSystem(node),
      preferred: isPreferred(node),
      describable: node.describable === true,
      summarizable: node.summarizable === true,
      holdsNodes: node.has_children === true,
      ...(node.kind === "schema" && node.frameworks?.length
        ? { frameworks: node.frameworks }
        : {}),
      // Only a table knows roughly how many rows it holds. A file would have
      // to be read from end to end to answer, so the grid pages without a
      // total.
      rowEstimate: node.kind === "table" ? node.row_count_estimate : null,
      ...(group === undefined ? {} : { group }),
    }
  })
}

/** The groupings among a level's children: what the filter above it offers. */
export function groupsOf(nodes: ListNode[]): ListNode[] {
  return nodes.filter((node) => node.role === "group")
}

/**
 * Whether the head of a level says where we are. Read off what the level
 * holds and never off the type of the source.
 *
 * A level that offers groupings already says one thing about itself on that
 * line; one that offers none has the line to itself. Drawing the path only
 * after the first step would make it appear and disappear while walking in
 * and out.
 */
export function showsPath(depth: number, groups: ListNode[]): boolean {
  return depth > 1 || groups.length === 0
}

/**
 * The path of the level standing on the node with this id.
 *
 * A level whose head draws a path is a level whose ids are paths below the
 * root of the connection, and a path is written from that root: "/" is the
 * root itself, which is a place like any other and not a level with nothing
 * to say. The same form the owner of the source stores as the folder their
 * connection points at, so what is copied here can be pasted there.
 */
export function levelPath(currentId: string | null): string {
  return `/${currentId ?? ""}`
}
