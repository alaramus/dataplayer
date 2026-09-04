import { Graph, layout } from "@dagrejs/dagre"
import type { EdgeLabel, GraphLabel, NodeLabel } from "@dagrejs/dagre"

import type { Camera2, GraphDocument, GraphEdge, GraphEndpoint, GraphNode, Point2, Point3 } from "./model"

export const CARD_WIDTH = 280
export const HEADER_HEIGHT = 52
export const ROW_HEIGHT = 24
export const nodeHeight = (node: GraphNode, expanded: boolean) => HEADER_HEIGHT + (expanded ? node.rows.length * ROW_HEIGHT : 0)

export function arrange(graph: GraphDocument, expanded: boolean) {
  const dag = new Graph<GraphLabel, NodeLabel, EdgeLabel>({ multigraph: true })
  dag.setGraph({ rankdir: "LR", ranksep: 140, nodesep: 64, marginx: 32, marginy: 32 })
  dag.setDefaultEdgeLabel(() => ({}))
  const ordered = [...graph.nodes].sort((a, b) => a.id.localeCompare(b.id))
  for (const node of ordered) dag.setNode(node.id, { width: CARD_WIDTH, height: nodeHeight(node, expanded) })
  for (const edge of [...graph.edges].sort((a, b) => a.id.localeCompare(b.id))) {
    dag.setEdge(edge.source.nodeId, edge.target.nodeId, {}, edge.id)
  }
  layout(dag)
  const positions2: Record<string, Point2> = Object.fromEntries(ordered.map((node) => {
    const placed = dag.node(node.id)
    return [node.id, { x: (placed.x ?? 0) - CARD_WIDTH / 2, y: (placed.y ?? 0) - nodeHeight(node, expanded) / 2 }]
  }))
  const groups = [...new Set(ordered.map((node) => node.groupId ?? ""))].sort()
  const positions3: Record<string, Point3> = Object.fromEntries(ordered.map((node) => {
    const point = positions2[node.id]!
    return [node.id, { x: point.x * 0.7, y: groups.indexOf(node.groupId ?? "") * 180, z: point.y * 0.55 }]
  }))
  return { positions2, positions3 }
}

export function fit2(graph: GraphDocument, positions: Record<string, Point2>, expanded: boolean, width: number, height: number): Camera2 {
  if (!graph.nodes.length || width <= 0 || height <= 0) return { x: 32, y: 32, zoom: 1 }
  const left = Math.min(...graph.nodes.map((node) => positions[node.id]!.x))
  const top = Math.min(...graph.nodes.map((node) => positions[node.id]!.y))
  const right = Math.max(...graph.nodes.map((node) => positions[node.id]!.x + CARD_WIDTH))
  const bottom = Math.max(...graph.nodes.map((node) => positions[node.id]!.y + nodeHeight(node, expanded)))
  const zoom = Math.max(0.03, Math.min(1, (width - 64) / (right - left), (height - 64) / (bottom - top)))
  return { zoom, x: width / 2 - (left + right) / 2 * zoom, y: height / 2 - (top + bottom) / 2 * zoom }
}

export function zoomAt(camera: Camera2, factor: number, point: Point2): Camera2 {
  const zoom = Math.max(0.03, Math.min(3, camera.zoom * factor))
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
    const a = anchor(edge.source, nodes, positions, expanded, right)
    const b = anchor(edge.target, nodes, positions, expanded, self || !right)
    let path: string
    if (self) {
      const offset = 60 + lane * 26
      const lift = 40 + lane * 18
      path = `M ${a.x} ${a.y} C ${a.x + offset} ${a.y - lift}, ${b.x + offset} ${b.y + lift}, ${b.x} ${b.y}`
    } else {
      const bend = Math.max(45, Math.abs(b.x - a.x) * 0.45) + lane * 26
      const direction = right ? 1 : -1
      path = `M ${a.x} ${a.y} C ${a.x + direction * bend} ${a.y + lane * 12}, ${b.x - direction * bend} ${b.y + lane * 12}, ${b.x} ${b.y}`
    }
    return { edge, path }
  })
}
