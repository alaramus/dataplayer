/** Presentation data only. Producers own the meaning and actions of a graph. */
export interface GraphRow {
  id: string
  label: string
  detail?: string
  badges?: readonly string[]
  /** Drawn where the badges are, for a row that is a kind of thing. */
  icon?: string
  /** Named, and not there any more. */
  muted?: boolean
  /** Not there yet: what something on the canvas will make. */
  made?: boolean
}
export interface GraphDetail { label: string; value: string }
export interface GraphNode {
  id: string
  label: string
  caption?: string
  groupId?: string
  rows: readonly GraphRow[]
  details?: readonly GraphDetail[]
  placeholder?: boolean
}
export interface GraphEndpoint { nodeId: string; portIds?: readonly string[] }
/** One row of one node, as a gesture names it. */
export interface GraphPort { nodeId: string; portId: string }
/** What a line says by its colour: at work, done, failed, or passed over. */
export type GraphEdgeTone = "info" | "success" | "error" | "muted"
export interface GraphEdge {
  id: string
  source: GraphEndpoint
  target: GraphEndpoint
  label: string
  directed: boolean
  dashed?: boolean
  details?: readonly GraphDetail[]
  tone?: GraphEdgeTone
  /** Written before the label and apart from it: a step's number. */
  badge?: string
  /** Why the badge is in the caution colour, said when it is pointed at. */
  caution?: string
}
export interface GraphGroup { id: string; label: string }
export interface GraphDocument {
  nodes: readonly GraphNode[]
  edges: readonly GraphEdge[]
  groups: readonly GraphGroup[]
}
export type GraphSelection = { kind: "node"; id: string; portId?: string }
  | { kind: "edge"; id: string } | null
export interface Point2 { x: number; y: number }
export interface Point3 extends Point2 { z: number }
export interface Camera2 extends Point2 { zoom: number }
export interface Camera3 { position: Point3; target: Point3 }
export interface GraphViewState {
  mode: "2d" | "3d"
  positions2: Record<string, Point2>
  positions3: Record<string, Point3>
  camera2: Camera2 | null
  camera3: Camera3 | null
  expanded: boolean
  labels: boolean
  groupId: string | null
}

export const GRAPH_LIMITS = { nodes: 300, rows: 5_000, edges: 1_000 } as const

export function graphProblem(graph: GraphDocument): string | null {
  if (graph.nodes.length > GRAPH_LIMITS.nodes || graph.edges.length > GRAPH_LIMITS.edges ||
    graph.nodes.reduce((count, node) => count + node.rows.length, 0) > GRAPH_LIMITS.rows) {
    return "This graph is too large. Select fewer objects."
  }
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]))
  if (nodes.size !== graph.nodes.length || new Set(graph.edges.map((edge) => edge.id)).size !== graph.edges.length) {
    return "This graph contains duplicate identities."
  }
  for (const node of graph.nodes) {
    if (new Set(node.rows.map((row) => row.id)).size !== node.rows.length) return "A node contains duplicate ports."
  }
  for (const edge of graph.edges) {
    for (const endpoint of [edge.source, edge.target]) {
      const node = nodes.get(endpoint.nodeId)
      if (!node || endpoint.portIds?.some((id) => !node.rows.some((row) => row.id === id))) {
        return "A connection points to an object or port that is missing."
      }
    }
  }
  return null
}

export function edgesOf(graph: GraphDocument, selected: GraphSelection): readonly GraphEdge[] {
  if (!selected) return []
  if (selected.kind === "edge") return graph.edges.filter((edge) => edge.id === selected.id)
  return graph.edges.filter((edge) => [edge.source, edge.target].some((end) =>
    end.nodeId === selected.id && (!selected.portId || end.portIds?.includes(selected.portId))
  ))
}

/**
 * One connection of a selected node, as its list shows it: which way it goes,
 * the node at the other end, and what the connection is. Without the other
 * end, forty arrows that each say "Save as CSV" are forty identical lines.
 */
export function relatedLabel(graph: GraphDocument, nodeId: string, edge: GraphEdge): string {
  const outgoing = edge.source.nodeId === nodeId
  const other = outgoing ? edge.target.nodeId : edge.source.nodeId
  const name = graph.nodes.find((node) => node.id === other)?.label ?? other
  const way = other === nodeId ? "↻" : outgoing ? "→" : "←"
  return `${way} ${name}: ${edge.label}`
}

export function neighborsOf(graph: GraphDocument, selected: GraphSelection): Set<string> {
  const found = new Set<string>()
  if (selected?.kind === "node") found.add(selected.id)
  for (const edge of edgesOf(graph, selected)) {
    found.add(edge.source.nodeId)
    found.add(edge.target.nodeId)
  }
  return found
}

export function groupGraph(graph: GraphDocument, groupId: string | null): GraphDocument {
  if (groupId === null) return graph
  const nodes = graph.nodes.filter((node) => node.groupId === groupId)
  const ids = new Set(nodes.map((node) => node.id))
  return { ...graph, nodes, edges: graph.edges.filter((edge) => ids.has(edge.source.nodeId) && ids.has(edge.target.nodeId)) }
}

export function accentIndex(node: GraphNode): number {
  let hash = 0
  for (const char of node.groupId ?? "default") hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return hash % 5 + 1
}
