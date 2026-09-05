import type {
  FetchColumn,
  FetchReference,
  NodeRepresentation,
  ReferencedRows,
  ReferenceValue,
} from "@/client"

/**
 * Where the way out of a row is drawn, and what is sent when it is pressed.
 *
 * Both are decisions about the screen. What the key means — which of the
 * target's columns each of these stands for, whether an empty one names
 * anything, whether the target can be looked up at all — belongs to the source
 * and is never worked out here. See D36.
 */

/**
 * The references this column carries the handle for.
 *
 * One handle per reference and not per column: a composite key spans several
 * columns and is one way out, so the arrow sits on the first of its columns
 * that is actually on screen. Hiding that column moves the arrow to the next
 * one rather than taking the way out away.
 */
export function referencesLedBy(
  references: readonly FetchReference[],
  columnName: string,
  visibleColumns: readonly string[]
): FetchReference[] {
  const onScreen = new Set(visibleColumns)
  return references.filter(
    (reference) => reference.columns.find((name) => onScreen.has(name)) === columnName
  )
}

/**
 * What one row holds for every column of one reference.
 *
 * Every column of the key, whatever the row has in it — a missing value is
 * sent as null rather than left out, because what an absent key names is the
 * source's answer and not this file's guess. Nothing is returned at all when
 * the page does not carry one of the columns, which is a page read before the
 * relation changed.
 */
export function keyValues(
  reference: FetchReference,
  columns: readonly FetchColumn[],
  values: readonly (string | null)[]
): ReferenceValue[] | null {
  const taken: ReferenceValue[] = []
  for (const name of reference.columns) {
    const index = columns.findIndex((column) => column.name === name)
    if (index === -1) return null
    taken.push({ column: name, value: values[index] ?? null })
  }
  return taken
}

/** A connection, as a tab needs to be told about one. */
export interface Landing {
  connectorId: string
  connectorName: string
  adapterType: string
}

/** The tab a followed reference opens, in the words `open` takes. */
export interface FollowedRows extends Landing {
  nodeId: string
  title: string
  describable: boolean
  representations: NodeRepresentation[]
}

/**
 * The connection a followed reference lands in.
 *
 * The answer names it, because a reference somebody drew can point into
 * another connection entirely and only the route knows which (D108). The tab
 * the click came from is the fallback, and inside one source it is the same
 * connection anyway.
 */
function landingConnection(target: ReferencedRows, asking: Landing): Landing {
  const landing = target.connector
  if (!landing) return asking
  return {
    connectorId: landing.id,
    connectorName: landing.name,
    adapterType: landing.adapter_type,
  }
}

/**
 * The whole tab, read off the node the source answered with.
 *
 * The answer carries a `CatalogNode` and not an id for exactly this reason
 * (D36): a tab arrived at by following a key is the same tab as one opened
 * from the catalog, so it says what it can be opened as and is drawn as
 * itself. Built here rather than in the workspace because the workspace had
 * assembled it by hand, dropped the representations, and every followed tab
 * was drawn as the logo of its source instead of as a table.
 */
export function followedRows(target: ReferencedRows, asking: Landing): FollowedRows {
  const node = target.node
  return {
    ...landingConnection(target, asking),
    nodeId: node.id,
    title: node.name,
    describable: node.describable === true,
    representations: node.representations,
  }
}
