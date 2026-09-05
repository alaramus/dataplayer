import type { DeclaredReferencePublic, FetchColumn, ReferenceEndPublic } from "@/client"

/**
 * What a screen needs to say about a reference somebody drew (D106).
 *
 * Plain functions rather than component code, so which end you are standing on
 * and what it can be drawn from are decided once and testable without a
 * browser. Nothing here decides what a reference means — that is the source's
 * answer, given when one is followed.
 */

/** Where you are standing, and where the reference goes from there. */
export interface Sides {
  near: ReferenceEndPublic
  far: ReferenceEndPublic
}

/**
 * The columns of a node a reference can stand on.
 *
 * Equality is what following one asks of a source, so a column that cannot be
 * looked up cannot be an end of one — and the server refuses it (D107). This
 * is the same rule said early enough to keep it out of the list.
 */
export function lookupColumns(columns: readonly FetchColumn[]): FetchColumn[] {
  return columns.filter((column) => column.filter_operators?.includes("eq") === true)
}

/**
 * The two ends of one reference, from the node being looked at.
 *
 * Nothing when neither end is this node, which is a list that has moved on
 * since it was read. A node referenced to itself is standing on the first of
 * the two, and both of its ways out are still on the page itself.
 */
export function sidesFrom(
  reference: DeclaredReferencePublic,
  connectorId: string,
  nodeId: string
): Sides | null {
  const [first, second] = reference.ends
  if (first.connector_id === connectorId && first.node_id === nodeId) {
    return { near: first, far: second }
  }
  if (second.connector_id === connectorId && second.node_id === nodeId) {
    return { near: second, far: first }
  }
  return null
}

/**
 * How the far end reads: its connection, its node and its column.
 *
 * The connection is named only when it is a different one — inside a single
 * source, repeating its name in every row says nothing.
 */
export function farLabel(far: ReferenceEndPublic, connectorId: string): string {
  const where = far.connector_id === connectorId ? "" : `${far.connector_name} · `
  return `${where}${far.node_label}.${far.column}`
}
