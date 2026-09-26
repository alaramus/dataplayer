/**
 * A pipeline's cards as the canvas draws them, and the changes made to them
 * (D175). Plain functions: the canvas holds the draft, these say what it
 * becomes.
 */

import type { Card, CardRow, CardState } from "@/client"
import { ICONS } from "@/features/catalog/nodes"
import { CARD_WIDTH, HEADER_HEIGHT, ROW_HEIGHT } from "@/shared/graph/layout"
import type { Camera2, GraphDocument, GraphEdge, GraphNode, GraphRow, Point2 } from "@/shared/graph/model"

/** What the list of connections says of the one a card is on. */
export interface CardConnection {
  name: string
  adapterType: string
  enabled: boolean
}

/** The icon of the top of a connection, which is no node of its own. */
export const TOP_ICON = "home_storage"

/** The dragged thing a connection is on its way to the canvas, by its id. */
export const CONNECTION_DRAG = "application/x-dataplayer-connection"

const KIND_WORDS: Record<NonNullable<CardRow["kind"]>, string> = {
  schema: "schema",
  table: "table",
  view: "view",
  directory: "folder",
  file: "file",
  dataset: "dataset",
  entry: "entry",
  report: "report",
  database: "database",
  key: "key",
}

/**
 * A row's id on the canvas. The top of a connection has no node id, and a
 * node's own id is prefixed so no source's id can be taken for it.
 */
export function rowId(nodeId: string | null | undefined): string {
  return nodeId == null ? "top" : `node:${nodeId}`
}

function rowOf(row: CardRow, missing: ReadonlySet<string>): GraphRow {
  const gone = row.node_id != null && missing.has(row.node_id)
  const where = (row.trail ?? []).join(" / ")
  return {
    id: rowId(row.node_id),
    label: row.label,
    detail: gone ? "not found" : where || (row.kind == null ? "top" : KIND_WORDS[row.kind]),
    icon: row.kind == null ? TOP_ICON : ICONS[row.kind],
    muted: gone,
  }
}

/**
 * Why a card cannot be worked with, or nothing: the server's word once it has
 * checked, the list of connections' until then.
 */
export function cardProblem(connection: CardConnection | undefined, state: CardState | undefined): string | null {
  if (state?.problem) return state.problem
  if (connection === undefined) return "This connection is gone, or no longer shared with you"
  if (!connection.enabled) return "This connection is switched off"
  return null
}

export function cardNode(
  card: Card,
  connection: CardConnection | undefined,
  state: CardState | undefined,
  typeTitle: string | undefined
): GraphNode {
  const problem = cardProblem(connection, state)
  const missing = new Set(state?.missing ?? [])
  return {
    id: card.id,
    label: connection?.name ?? card.connector_name,
    caption: problem ?? typeTitle ?? connection?.adapterType ?? "",
    // One accent a connection, so its cards are seen to be one source.
    groupId: card.connector_id,
    rows: card.rows.map((row) => rowOf(row, missing)),
    placeholder: problem !== null,
  }
}

export function pipelineGraph(
  cards: readonly Card[],
  connections: ReadonlyMap<string, CardConnection>,
  states: ReadonlyMap<string, CardState>,
  typeTitles: ReadonlyMap<string, string>,
  edges: readonly GraphEdge[] = []
): GraphDocument {
  return {
    nodes: cards.map((card) => {
      const connection = connections.get(card.connector_id)
      return cardNode(
        card,
        connection,
        states.get(card.id),
        connection === undefined ? undefined : typeTitles.get(connection.adapterType)
      )
    }),
    edges,
    groups: [],
  }
}

export function positionsOf(cards: readonly Card[]): Record<string, Point2> {
  return Object.fromEntries(cards.map((card) => [card.id, { x: card.x, y: card.y }]))
}

/** A point of the canvas, from a point of its box on the screen. */
export function worldPoint(camera: Camera2, screen: Point2): Point2 {
  return { x: (screen.x - camera.x) / camera.zoom, y: (screen.y - camera.y) / camera.zoom }
}

/** Where a card goes for a drop at this point: centred under the pointer's head. */
export function dropSpot(point: Point2): Point2 {
  return { x: Math.round(point.x - CARD_WIDTH / 2), y: Math.round(point.y - HEADER_HEIGHT / 2) }
}

// Room left between two cards placed for the person: below, so neither hides
// the other's head; beside, so a link between them and its label have
// somewhere to run.
const GAP = 48
const ACROSS = 120
const REACH = 6

function heightOf(rows: number): number {
  return HEADER_HEIGHT + rows * ROW_HEIGHT
}

/**
 * The nearest place to this one where a card of so many rows covers no other
 * card. A card pressed into the middle of the view would otherwise land on
 * whatever is there already, and two cards over each other read as one.
 *
 * Beside before below: a link is drawn from the right edge of one card to
 * the left edge of the next, and cards stacked in a column make every link
 * loop round them.
 */
export function freeSpot(cards: readonly Card[], point: Point2, rows: number): Point2 {
  const height = heightOf(rows)
  const clashes = (spot: Point2) =>
    cards.some((card) =>
      spot.x < card.x + CARD_WIDTH + ACROSS && card.x < spot.x + CARD_WIDTH + ACROSS &&
      spot.y < card.y + heightOf(card.rows.length) + GAP && card.y < spot.y + height + GAP
    )
  // Right before left, and a step down costs two steps across; the sort keeps
  // this order among equals.
  const steps = [0, ...Array.from({ length: REACH }, (_, n) => [n + 1, -(n + 1)]).flat()]
  const spots = steps.flatMap((down) => steps.map((across) => ({ across, down })))
  spots.sort((a, b) => Math.abs(a.across) + 2 * Math.abs(a.down) - (Math.abs(b.across) + 2 * Math.abs(b.down)))
  const found = spots
    .map(({ across, down }) => ({ x: point.x + across * (CARD_WIDTH + ACROSS), y: point.y + down * (HEADER_HEIGHT + GAP) }))
    .find((spot) => !clashes(spot))
  return found ?? point
}

const MARGIN = 16

/**
 * The camera moved just enough for a card of so many rows at this spot to be
 * wholly in a view of this size; unmoved when it already is. Never zoomed: a
 * card placed should not change how big everything else looks.
 */
export function revealing(camera: Camera2, view: { width: number; height: number }, spot: Point2, rows: number): Camera2 {
  const left = spot.x * camera.zoom + camera.x
  const top = spot.y * camera.zoom + camera.y
  const right = left + CARD_WIDTH * camera.zoom
  const bottom = top + heightOf(rows) * camera.zoom
  const dx = right > view.width - MARGIN ? view.width - MARGIN - right : left < MARGIN ? MARGIN - left : 0
  const dy = bottom > view.height - MARGIN ? view.height - MARGIN - bottom : top < MARGIN ? MARGIN - top : 0
  return dx === 0 && dy === 0 ? camera : { ...camera, x: camera.x + dx, y: camera.y + dy }
}

export function movedCard(cards: readonly Card[], id: string, point: Point2): Card[] {
  return cards.map((card) => (card.id === id ? { ...card, x: Math.round(point.x), y: Math.round(point.y) } : card))
}

export function withRows(cards: readonly Card[], id: string, rows: CardRow[]): Card[] {
  return cards.map((card) => (card.id === id ? { ...card, rows } : card))
}

export function withoutCard(cards: readonly Card[], id: string): Card[] {
  return cards.filter((card) => card.id !== id)
}

/** What a card's check is asked by: it answers for these rows and no others. */
export function checkedRowsKey(card: Card): string {
  return card.rows.map((row) => rowId(row.node_id)).join("\u0000")
}

/** The name a new pipeline starts with, as a new dashboard's does. */
export function newPipelineName(count: number): string {
  return count === 0 ? "My pipeline" : `Pipeline ${String(count + 1)}`
}
