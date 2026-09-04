import type { RelationModel } from "@/client"
import { badgesFor } from "@/features/structure/model"
import type { GraphDocument, GraphEdge, GraphNode } from "@/shared/graph/model"

export const MAX_RELATIONS = 100
export interface DiagramNodeRef { id: string; label: string }
export interface RelationFailure extends DiagramNodeRef { message: string }
export interface RelationGraphSource {
  requested: DiagramNodeRef[]
  models: RelationModel[]
  failures: RelationFailure[]
}

export function diagramNodes(checked: readonly (DiagramNodeRef & { describable: boolean })[], visible: readonly (DiagramNodeRef & { describable: boolean })[]): DiagramNodeRef[] {
  return (checked.length ? checked : visible).filter((node) => node.describable).map(({ id, label }) => ({ id, label }))
}

export function relationshipPanelId(connectorId: string, nodes: readonly DiagramNodeRef[]): string {
  return `relationships:${JSON.stringify([connectorId, [...new Set(nodes.map((node) => node.id))].sort()])}`
}

/** Only this producer understands relations, columns or foreign keys. */
export function relationGraph(source: RelationGraphSource): GraphDocument {
  const models = new Map(source.models.map((model) => [model.node_id, model]))
  const nodes = new Map<string, GraphNode>()
  const edges: GraphEdge[] = []
  const groups = new Map<string, string>()
  for (const requested of source.requested) {
    const model = models.get(requested.id)
    if (!model) {
      const failure = source.failures.find((item) => item.id === requested.id)
      nodes.set(requested.id, {
        id: requested.id, label: requested.label, caption: "Structure unavailable", rows: [], placeholder: true,
        details: [{ label: "Read error", value: failure?.message ?? "This structure could not be read." }],
      })
      continue
    }
    const groupId = model.schema_name || undefined
    if (groupId) groups.set(groupId, groupId)
    nodes.set(model.node_id, {
      id: model.node_id, label: model.name, caption: [model.schema_name, model.kind.replaceAll("_", " ")].filter(Boolean).join(" · "), groupId,
      rows: [...(model.columns ?? [])].sort((a, b) => a.position - b.position).map((column) => ({
        id: column.name, label: column.name, detail: `${column.type.sql}${column.nullable ? "" : " · NOT NULL"}`,
        badges: [...new Set(badgesFor(model, column.name).filter((badge) => badge.kind !== "index").map((badge) => badge.label))],
      })),
      details: [
        ...(model.comment ? [{ label: "Description", value: model.comment }] : []),
        ...(model.owner ? [{ label: "Owner", value: model.owner }] : []),
      ],
    })
  }
  for (const model of source.models) {
    for (const key of model.constraints ?? []) {
      if (key.kind !== "foreign_key") continue
      if (!nodes.has(key.target_node_id)) {
        nodes.set(key.target_node_id, {
          id: key.target_node_id, label: key.target_node_id, caption: "Outside selection", rows: [], placeholder: true,
          details: [{ label: "Scope", value: "This table is referenced by the selection. Its structure has not been loaded." }],
        })
      }
      const sourceRows = nodes.get(model.node_id)!.rows
      const targetRows = nodes.get(key.target_node_id)!.rows
      const sourcePorts = key.columns.filter((name) => sourceRows.some((row) => row.id === name))
      const targetPorts = key.target_columns.filter((name) => targetRows.some((row) => row.id === name))
      edges.push({
        id: JSON.stringify([model.node_id, key.name]), label: key.name,
        source: { nodeId: model.node_id, portIds: sourcePorts },
        target: { nodeId: key.target_node_id, portIds: targetPorts },
        directed: true, dashed: key.validated === false || !models.has(key.target_node_id),
        details: [
          { label: "Columns", value: key.columns.map((name, index) => `${name} → ${key.target_columns[index] ?? "?"}`).join("\n") },
          { label: "On update", value: (key.on_update ?? "no_action").replaceAll("_", " ") },
          { label: "On delete", value: (key.on_delete ?? "no_action").replaceAll("_", " ") },
          { label: "Validated", value: key.validated === false ? "No" : "Yes" },
        ],
      })
    }
  }
  return { nodes: [...nodes.values()], edges, groups: [...groups].map(([id, label]) => ({ id, label })) }
}
