/**
 * The map of what connections can give each other, as a graph (D174).
 *
 * The server answers with the connections and, per direction, the kinds of
 * paste that serve it and whether each is open to this person; this only
 * draws that answer, and names no kind.
 */

import type { InteractionMap, MapArrow, MapConnection } from "@/client"
import type { GraphDocument, GraphEdge, GraphNode } from "@/shared/graph/model"

const ACCESS_WORDS: Record<MapConnection["access"], string> = {
  read: "Read",
  write: "Write",
  structure: "Structure",
  own: "Owner",
}

export function arrowId(arrow: Pick<MapArrow, "source_connector_id" | "destination_connector_id">): string {
  return `${arrow.source_connector_id}>${arrow.destination_connector_id}`
}

function nodeOf(connection: MapConnection): GraphNode {
  return {
    id: connection.id,
    label: connection.name,
    caption: connection.type_title,
    groupId: connection.category,
    rows: [],
    details: [
      { label: "Type", value: connection.type_title },
      { label: "Your access", value: ACCESS_WORDS[connection.access] },
    ],
  }
}

function edgeOf(arrow: MapArrow): GraphEdge {
  const open = arrow.operations.some((operation) => operation.available)
  return {
    id: arrowId(arrow),
    source: { nodeId: arrow.source_connector_id },
    target: { nodeId: arrow.destination_connector_id },
    label: arrow.operations.map((operation) => operation.title).join(" · "),
    directed: true,
    // Possible between such connections, and nothing of it open to this
    // person: drawn, so what is missing can be read off it.
    dashed: !open,
    details: arrow.operations.map((operation) => ({
      label: operation.title,
      value: operation.available ? "Open to you" : operation.reason ?? "Not open to you",
    })),
  }
}

export function mapGraph(map: InteractionMap): GraphDocument {
  const groups = new Map<string, string>()
  for (const connection of map.connections) groups.set(connection.category, connection.category_title)
  return {
    nodes: map.connections.map(nodeOf),
    edges: map.arrows.map(edgeOf),
    groups: [...groups].map(([id, label]) => ({ id, label })),
  }
}

/** The two ends of an arrow the graph names by its id, or nothing. */
export function endsOf(map: InteractionMap, edgeId: string): { source: string; destination: string } | null {
  const arrow = map.arrows.find((one) => arrowId(one) === edgeId)
  return arrow === undefined
    ? null
    : { source: arrow.source_connector_id, destination: arrow.destination_connector_id }
}
