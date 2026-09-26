/**
 * What is ticked in a card's window: the rows the card will hold (D175).
 *
 * Ticks outlive the level they were made on, since a card holds tables of two
 * schemas as easily as one, so they are kept as rows rather than as the ids
 * of whatever the window shows now.
 */

import type { CardRow } from "@/client"
import type { ListNode } from "@/features/catalog/nodes"

import { rowId } from "./model"

/**
 * The server's bound on a card (MAX_ROWS), said here so the hundred-and-first
 * tick is stopped where it is made rather than the save refused.
 */
export const MAX_CARD_ROWS = 100

export const TOO_MANY = `A card holds at most ${String(MAX_CARD_ROWS)} rows`

export function isTicked(rows: readonly CardRow[], nodeId: string | null): boolean {
  const id = rowId(nodeId)
  return rows.some((row) => rowId(row.node_id) === id)
}

function rowFor(node: ListNode, trail: readonly string[]): CardRow {
  return { node_id: node.id, label: node.label, kind: node.kind, trail: [...trail] }
}

export function topRow(connectionName: string): CardRow {
  return { node_id: null, label: connectionName, kind: null, trail: [] }
}

/** The rows with this one ticked or not, or why it cannot be. */
export function ticked(rows: readonly CardRow[], row: CardRow, on: boolean): CardRow[] | string {
  const id = rowId(row.node_id)
  const without = rows.filter((one) => rowId(one.node_id) !== id)
  if (!on) return without
  if (without.length >= MAX_CARD_ROWS) return TOO_MANY
  return [...without, row]
}

export function tickedNode(
  rows: readonly CardRow[], node: ListNode, trail: readonly string[], on: boolean
): CardRow[] | string {
  return ticked(rows, rowFor(node, trail), on)
}

/** Every node shown ticked or unticked at once; all or none, never half. */
export function tickedAll(
  rows: readonly CardRow[], nodes: readonly ListNode[], trail: readonly string[], on: boolean
): CardRow[] | string {
  if (!on) {
    const shown = new Set(nodes.map((node) => rowId(node.id)))
    return rows.filter((row) => !shown.has(rowId(row.node_id)))
  }
  const held = new Set(rows.map((row) => rowId(row.node_id)))
  const all = [...rows, ...nodes.filter((node) => !held.has(rowId(node.id))).map((node) => rowFor(node, trail))]
  return all.length > MAX_CARD_ROWS ? TOO_MANY : all
}

/** Where a ticked row lives, for the list of what is ticked. */
export function whereOf(row: CardRow): string {
  return (row.trail ?? []).join(" / ")
}
