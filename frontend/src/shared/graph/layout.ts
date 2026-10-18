import { Graph, layout } from "@dagrejs/dagre"
import type { EdgeLabel, GraphLabel, NodeLabel } from "@dagrejs/dagre"

import type { Camera2, GraphDocument, GraphEdge, GraphEndpoint, GraphNode, Point2, Point3 } from "./model"
import { arrange3 } from "./layout3d"

export const CARD_WIDTH = 280
export const HEADER_HEIGHT = 52
export const ROW_HEIGHT = 24
export const nodeHeight = (node: GraphNode, expanded: boolean) => HEADER_HEIGHT + (expanded ? node.rows.length * ROW_HEIGHT : 0)

/** The rough shape packed groups aim at: a screen's, not a column's. */
const TARGET_ASPECT = 16 / 9
/** Between two packed groups: a rank's gap, so a group reads as one. */
const GROUP_GAP = 140
const MARGIN = 32

interface Block {
  /** Positions inside the block, its top left corner at 0, 0. */
  positions: Record<string, Point2>
  width: number
  height: number
}

/** Nodes joined by any edge, each group in a stable order; a node alone is a group of one. */
function groups(graph: GraphDocument): string[][] {
  const parent = new Map(graph.nodes.map((node) => [node.id, node.id]))
  const root = (id: string): string => {
    let at = id
    while (parent.get(at) !== at) at = parent.get(at)!
    parent.set(id, at)
    return at
  }
  for (const edge of graph.edges) {
    if (!parent.has(edge.source.nodeId) || !parent.has(edge.target.nodeId)) continue
    const a = root(edge.source.nodeId)
    const b = root(edge.target.nodeId)
    if (a !== b) parent.set(a < b ? b : a, a < b ? a : b)
  }
  const byRoot = new Map<string, string[]>()
  for (const node of [...graph.nodes].sort((a, b) => a.id.localeCompare(b.id))) {
    const key = root(node.id)
    byRoot.set(key, [...(byRoot.get(key) ?? []), node.id])
  }
  return [...byRoot.values()]
}

const RANK_GAP = 140
const NODE_GAP = 64

/**
 * A rank too tall for the target shape, as several columns side by side, in
 * Dagre's order. A schema where every table names its owner puts forty cards
 * in the one rank before `user`: packing whole groups cannot shorten a group
 * that is itself a column. Cards in one rank have no key between them, so
 * splitting it crosses no edge.
 */
function wrapRanks(nodes: readonly GraphNode[], positions: Record<string, Point2>, expanded: boolean): Record<string, Point2> {
  const byRank = new Map<number, GraphNode[]>()
  for (const node of nodes) {
    const x = Math.round(positions[node.id]!.x)
    byRank.set(x, [...(byRank.get(x) ?? []), node])
  }
  const ranks = [...byRank.entries()].sort(([a], [b]) => a - b)
    .map(([, members]) => members.sort((a, b) => positions[a.id]!.y - positions[b.id]!.y))
  const height = (members: readonly GraphNode[]) =>
    members.reduce((sum, node) => sum + nodeHeight(node, expanded), 0) + NODE_GAP * (members.length - 1)
  const columnsOf = (members: readonly GraphNode[], perColumn: number) =>
    Array.from({ length: Math.ceil(members.length / perColumn) }, (_, i) => members.slice(i * perColumn, (i + 1) * perColumn))
  const shapeOf = (perColumn: number) => {
    const columns = ranks.map((members) => columnsOf(members, perColumn))
    const count = columns.reduce((sum, rank) => sum + rank.length, 0)
    const width = count * (CARD_WIDTH + NODE_GAP) - NODE_GAP + (ranks.length - 1) * (RANK_GAP - NODE_GAP)
    return { columns, width, height: Math.max(...columns.flat().map(height)) }
  }
  const tallest = Math.max(...ranks.map((members) => members.length))
  let best = shapeOf(tallest)
  for (let perColumn = tallest - 1; perColumn >= 3; perColumn--) {
    const shape = shapeOf(perColumn)
    const miss = (one: { width: number; height: number }) => Math.abs(Math.log(one.width / one.height / TARGET_ASPECT))
    if (miss(shape) < miss(best)) best = shape
  }
  const placed: Record<string, Point2> = {}
  let x = 0
  for (const rank of best.columns) {
    for (const column of rank) {
      let y = (best.height - height(column)) / 2
      for (const node of column) {
        placed[node.id] = { x, y }
        y += nodeHeight(node, expanded) + NODE_GAP
      }
      x += CARD_WIDTH + NODE_GAP
    }
    x += RANK_GAP - NODE_GAP
  }
  return placed
}

function dagreBlock(graph: GraphDocument, ids: readonly string[], expanded: boolean): Block {
  const members = new Set(ids)
  const nodes = graph.nodes.filter((node) => members.has(node.id)).sort((a, b) => a.id.localeCompare(b.id))
  const dag = new Graph<GraphLabel, NodeLabel, EdgeLabel>({ multigraph: true })
  dag.setGraph({ rankdir: "LR", ranksep: RANK_GAP, nodesep: NODE_GAP, marginx: 0, marginy: 0 })
  dag.setDefaultEdgeLabel(() => ({}))
  for (const node of nodes) dag.setNode(node.id, { width: CARD_WIDTH, height: nodeHeight(node, expanded) })
  for (const edge of [...graph.edges].sort((a, b) => a.id.localeCompare(b.id))) {
    if (members.has(edge.source.nodeId) && members.has(edge.target.nodeId)) {
      dag.setEdge(edge.source.nodeId, edge.target.nodeId, {}, edge.id)
    }
  }
  layout(dag)
  const positions = Object.fromEntries(nodes.map((node) => {
    const placed = dag.node(node.id)
    return [node.id, { x: (placed.x ?? 0) - CARD_WIDTH / 2, y: (placed.y ?? 0) - nodeHeight(node, expanded) / 2 }]
  }))
  return normalised(wrapRanks(nodes, positions, expanded), nodes, expanded)
}

/** Nodes with no edge at all, as one grid of the target shape rather than one card each. */
function gridBlock(graph: GraphDocument, ids: readonly string[], expanded: boolean): Block {
  const nodes = graph.nodes.filter((node) => ids.includes(node.id)).sort((a, b) => a.id.localeCompare(b.id))
  const cell = Math.max(...nodes.map((node) => nodeHeight(node, expanded)))
  const columns = Math.max(1, Math.round(Math.sqrt(nodes.length * TARGET_ASPECT * (cell + 64) / (CARD_WIDTH + 64))))
  const positions = Object.fromEntries(nodes.map((node, index) => [
    node.id,
    { x: (index % columns) * (CARD_WIDTH + 64), y: Math.floor(index / columns) * (cell + 64) },
  ]))
  return normalised(positions, nodes, expanded)
}

function normalised(positions: Record<string, Point2>, nodes: readonly GraphNode[], expanded: boolean): Block {
  const left = Math.min(...nodes.map((node) => positions[node.id]!.x))
  const top = Math.min(...nodes.map((node) => positions[node.id]!.y))
  const moved = Object.fromEntries(nodes.map((node) => [node.id, { x: positions[node.id]!.x - left, y: positions[node.id]!.y - top }]))
  return {
    positions: moved,
    width: Math.max(...nodes.map((node) => moved[node.id]!.x + CARD_WIDTH)),
    height: Math.max(...nodes.map((node) => moved[node.id]!.y + nodeHeight(node, expanded))),
  }
}

/**
 * Blocks in rows, tallest first, each row as wide as the whole should be for
 * the target shape. One pass of Dagre over a whole database put every table
 * in two or three ranks, a column dozens of cards tall that Fit could only
 * show too small to read.
 */
function pack(blocks: readonly Block[]): Record<string, Point2> {
  const area = blocks.reduce((sum, block) => sum + (block.width + GROUP_GAP) * (block.height + GROUP_GAP), 0)
  const rowWidth = Math.max(...blocks.map((block) => block.width), Math.sqrt(area * TARGET_ASPECT))
  const positions: Record<string, Point2> = {}
  let x = 0
  let y = 0
  let rowHeight = 0
  for (const block of blocks) {
    if (x > 0 && x + block.width > rowWidth) {
      x = 0
      y += rowHeight + GROUP_GAP
      rowHeight = 0
    }
    for (const [id, point] of Object.entries(block.positions)) {
      positions[id] = { x: MARGIN + x + point.x, y: MARGIN + y + point.y }
    }
    x += block.width + GROUP_GAP
    rowHeight = Math.max(rowHeight, block.height)
  }
  return positions
}

export function arrange(graph: GraphDocument, expanded: boolean) {
  const found = groups(graph)
  const linked = found.filter((ids) => ids.length > 1)
  const alone = found.filter((ids) => ids.length === 1).flat()
  const blocks = [
    ...linked.map((ids) => dagreBlock(graph, ids, expanded)).sort((a, b) => b.height - a.height),
    ...(alone.length ? [gridBlock(graph, alone, expanded)] : []),
  ]
  const positions2: Record<string, Point2> = blocks.length ? pack(blocks) : {}
  const positions3: Record<string, Point3> = arrange3(graph, positions2)
  return { positions2, positions3 }
}

/** How far out a diagram is ever drawn, by Fit and by the wheel alike. */
const MIN_ZOOM = 0.03

export function fit2(graph: GraphDocument, positions: Record<string, Point2>, expanded: boolean, width: number, height: number): Camera2 {
  if (!graph.nodes.length || width <= 0 || height <= 0) return { x: 32, y: 32, zoom: 1 }
  const left = Math.min(...graph.nodes.map((node) => positions[node.id]!.x))
  const top = Math.min(...graph.nodes.map((node) => positions[node.id]!.y))
  const right = Math.max(...graph.nodes.map((node) => positions[node.id]!.x + CARD_WIDTH))
  const bottom = Math.max(...graph.nodes.map((node) => positions[node.id]!.y + nodeHeight(node, expanded)))
  const whole = Math.min(1, (width - 64) / (right - left), (height - 64) / (bottom - top))
  const zoom = Math.max(MIN_ZOOM, whole)
  // Held at the floor, the diagram does not fit: it opens at its top left
  // corner, where the reading starts, rather than centred on its middle.
  if (zoom > whole) return { zoom, x: 32 - left * zoom, y: 32 - top * zoom }
  return { zoom, x: width / 2 - (left + right) / 2 * zoom, y: height / 2 - (top + bottom) / 2 * zoom }
}

export function zoomAt(camera: Camera2, factor: number, point: Point2): Camera2 {
  const zoom = Math.max(MIN_ZOOM, Math.min(3, camera.zoom * factor))
  const ratio = zoom / camera.zoom
  return { zoom, x: point.x - (point.x - camera.x) * ratio, y: point.y - (point.y - camera.y) * ratio }
}

function anchor(endpoint: GraphEndpoint, nodes: Map<string, GraphNode>, positions: Record<string, Point2>, expanded: boolean, right: boolean): Point2 {
  const node = nodes.get(endpoint.nodeId)!
  const point = positions[node.id]!
  const indices = expanded ? (endpoint.portIds ?? []).map((id) => node.rows.findIndex((row) => row.id === id)).filter((index) => index >= 0) : []
  const y = indices.length ? HEADER_HEIGHT + (indices.reduce((sum, i) => sum + i, 0) / indices.length + 0.5) * ROW_HEIGHT : HEADER_HEIGHT / 2
  return { x: point.x + (right ? CARD_WIDTH : 0), y: point.y + y }
}

/** One end of a drawn edge: whose ports it holds, and which side it left by. */
export interface EdgeEnd {
  nodeId: string
  portIds: readonly string[]
  right: boolean
}

/**
 * Where a card's ports are drawn, from the same anchors the curves use.
 *
 * A field that no key names has nothing arriving at it, and a dot on every row
 * of every card was noise the eye had to read past. Which side is not a
 * property of the field either: it follows from where the other card sits, so
 * it is answered by the geometry rather than guessed a second time.
 */
export function portAnchors(paths: readonly { ends: readonly EdgeEnd[] }[]) {
  // Node, then port, rather than one key built from both: this is read twice
  // per row while the canvas is being panned, and a composed key would build a
  // string for every field of every card on every frame.
  const sides = new Map<string, Map<string, { left: boolean; right: boolean }>>()
  for (const path of paths) {
    for (const end of path.ends) {
      // An edge that names no port on this end is drawn from the header and
      // leaves the card without an entry of its own.
      for (const portId of end.portIds) {
        let ports = sides.get(end.nodeId)
        if (ports === undefined) {
          ports = new Map()
          sides.set(end.nodeId, ports)
        }
        const found = ports.get(portId) ?? { left: false, right: false }
        found[end.right ? "right" : "left"] = true
        ports.set(portId, found)
      }
    }
  }
  return sides
}

/** Stable lanes keep parallel and self references individually selectable. */
export function edgePaths(graph: GraphDocument, positions: Record<string, Point2>, expanded: boolean) {
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]))
  const lanes = new Map<string, number>()
  return graph.edges.map((edge: GraphEdge) => {
    const key = JSON.stringify([edge.source.nodeId, edge.target.nodeId].sort())
    const lane = lanes.get(key) ?? 0
    lanes.set(key, lane + 1)
    const self = edge.source.nodeId === edge.target.nodeId
    const right = self || positions[edge.target.nodeId]!.x >= positions[edge.source.nodeId]!.x + CARD_WIDTH
    const ends: EdgeEnd[] = [
      { nodeId: edge.source.nodeId, portIds: edge.source.portIds ?? [], right },
      { nodeId: edge.target.nodeId, portIds: edge.target.portIds ?? [], right: self || !right },
    ]
    const a = anchor(edge.source, nodes, positions, expanded, right)
    const b = anchor(edge.target, nodes, positions, expanded, self || !right)
    let c1: Point2
    let c2: Point2
    if (self) {
      const offset = 60 + lane * 26
      const lift = 40 + lane * 18
      c1 = { x: a.x + offset, y: a.y - lift }
      c2 = { x: b.x + offset, y: b.y + lift }
    } else {
      const bend = Math.max(45, Math.abs(b.x - a.x) * 0.45) + lane * 26
      const direction = right ? 1 : -1
      c1 = { x: a.x + direction * bend, y: a.y + lane * 12 }
      c2 = { x: b.x - direction * bend, y: b.y + lane * 12 }
    }
    const path = `M ${a.x} ${a.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${b.x} ${b.y}`
    const curve: Curve = [a, c1, c2, b]
    // The curve's own middle, where a label is written on it.
    return { edge, path, ends, mid: along(curve, 0.5), curve }
  })
}

/** A cubic curve by its ends and its two control points. */
export type Curve = readonly [Point2, Point2, Point2, Point2]

/** The point of a curve a share `t` of the way along it. */
export function along([a, c1, c2, b]: Curve, t: number): Point2 {
  const u = 1 - t
  const [wa, w1, w2, wb] = [u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t]
  return { x: wa * a.x + w1 * c1.x + w2 * c2.x + wb * b.x, y: wa * a.y + w1 * c1.y + w2 * c2.y + wb * b.y }
}

/** A label's box, as the canvas writes it: 11px text, a line high. */
const LABEL_HEIGHT = 16
const LABEL_CHAR = 6.5
/** Where along its line a label is tried, the middle first. */
const LABEL_STOPS = [0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8]

/** How many label heights above or below its middle a label may be stacked. */
const LABEL_STACK = 6

/**
 * Where each label is written: the middle of its line, or, where that would
 * cover a label already placed, the nearest point along its own line that
 * does not, and failing that a clear place stacked above or below the
 * middle. Two lines from one row to neighbouring rows share a middle, and the
 * second label hid the first, number and all.
 */
export function labelSpots(items: readonly { id: string; text: string; curve: Curve }[]): Map<string, Point2> {
  const placed: { x: number; y: number; width: number }[] = []
  const clear = (spot: Point2, width: number) => placed.every((box) =>
    Math.abs(box.x - spot.x) * 2 >= box.width + width || Math.abs(box.y - spot.y) >= LABEL_HEIGHT)
  const spots = new Map<string, Point2>()
  for (const item of items) {
    const width = item.text.length * LABEL_CHAR
    const middle = along(item.curve, 0.5)
    const stacked = Array.from({ length: LABEL_STACK }, (_, n) => [n + 1, -(n + 1)]).flat()
      .map((step) => ({ x: middle.x, y: middle.y + step * LABEL_HEIGHT }))
    const spot = [...LABEL_STOPS.map((t) => along(item.curve, t)), ...stacked]
      .find((one) => clear(one, width)) ?? middle
    placed.push({ ...spot, width })
    spots.set(item.id, spot)
  }
  return spots
}
