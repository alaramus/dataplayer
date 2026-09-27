import type { DeclaredReferencePublic, ReferenceEndPublic, RelationModel } from "@/client"
import { badgesFor } from "@/features/structure/model"
import type { GraphDocument, GraphEdge, GraphNode, GraphRow } from "@/shared/graph/model"

export const MAX_RELATIONS = 100
export interface DiagramNodeRef {
  id: string
  label: string
  /**
   * Drawn as the relations directly inside it rather than as itself: a
   * workbook is not a relation, and its sheets are (D51).
   */
  holdsNodes?: boolean
  /** The group it is drawn in when it is not its schema: the workbook it came from. */
  group?: string
}
export interface RelationFailure extends DiagramNodeRef { message: string }
/**
 * A relation at the far end of a declared reference that the selection does
 * not hold, read from its own connection so the line meets a column (D106).
 */
export interface FarRelation {
  connectorId: string
  connectorName: string
  adapterType: string
  nodeId: string
  label: string
  model: RelationModel | null
  message?: string
}
export interface RelationGraphSource {
  requested: DiagramNodeRef[]
  models: RelationModel[]
  failures: RelationFailure[]
  /** The connection the diagram is of; a node of any other is keyed apart. */
  connectorId?: string
  /** The declared references with an end among `models`. */
  declared?: DeclaredReferencePublic[]
  far?: FarRelation[]
}

type Candidate = DiagramNodeRef & { describable: boolean; readable?: boolean }

/**
 * What a diagram is drawn of: the ticks, or everything the filter left. A node
 * that opens and holds nodes of its own — a workbook — goes in to be drawn as
 * what it holds.
 */
export function diagramNodes(checked: readonly Candidate[], visible: readonly Candidate[]): DiagramNodeRef[] {
  return (checked.length ? checked : visible).flatMap((node) => {
    if (node.describable) return [{ id: node.id, label: node.label }]
    if (node.holdsNodes === true && node.readable === true) return [{ id: node.id, label: node.label, holdsNodes: true }]
    return []
  })
}

export function relationshipPanelId(connectorId: string, nodes: readonly DiagramNodeRef[]): string {
  return `relationships:${JSON.stringify([connectorId, [...new Set(nodes.map((node) => node.id))].sort()])}`
}

/**
 * The graph id of a node. A node of the diagram's own connection keeps its id,
 * which is what saved layouts are keyed by; one of another connection is keyed
 * with its connection, since two connections can hold the same id.
 */
export function graphIdOf(home: string | undefined, connectorId: string, nodeId: string): string {
  return home === undefined || connectorId === home ? nodeId : JSON.stringify([connectorId, nodeId])
}

function rowsOf(model: RelationModel): GraphRow[] {
  return [...(model.columns ?? [])].sort((a, b) => a.position - b.position).map((column) => ({
    id: column.name, label: column.name, detail: `${column.type.sql}${column.nullable ? "" : " · NOT NULL"}`,
    badges: [...new Set(badgesFor(model, column.name).filter((badge) => badge.kind !== "index").map((badge) => badge.label))],
  }))
}

function detailsOf(model: RelationModel) {
  return [
    ...(model.comment ? [{ label: "Description", value: model.comment }] : []),
    ...(model.owner ? [{ label: "Owner", value: model.owner }] : []),
  ]
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
    const groupId = requested.group ?? (model.schema_name || undefined)
    if (groupId) groups.set(groupId, groupId)
    nodes.set(model.node_id, {
      id: model.node_id, label: model.name, caption: [groupId, model.kind.replaceAll("_", " ")].filter(Boolean).join(" · "), groupId,
      rows: rowsOf(model), details: detailsOf(model),
    })
  }
  // Before the foreign keys, so one that reaches a relation read for a
  // declared reference meets its card rather than a placeholder.
  for (const far of source.far ?? []) {
    const id = graphIdOf(source.connectorId, far.connectorId, far.nodeId)
    if (nodes.has(id)) continue
    const elsewhere = source.connectorId !== undefined && far.connectorId !== source.connectorId
    const groupId = elsewhere ? JSON.stringify(["connection", far.connectorId]) : (far.model?.schema_name || undefined)
    if (groupId) groups.set(groupId, elsewhere ? far.connectorName : groupId)
    nodes.set(id, far.model
      ? {
          id, label: far.model.name, groupId,
          caption: [elsewhere ? far.connectorName : far.model.schema_name, far.model.kind.replaceAll("_", " ")].filter(Boolean).join(" · "),
          rows: rowsOf(far.model), details: detailsOf(far.model),
        }
      : {
          id, label: far.label, groupId, caption: "Structure unavailable", rows: [], placeholder: true,
          details: [{ label: "Read error", value: far.message ?? "This structure could not be read." }],
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
  // Undirected: neither end of a declared reference is the key (D106).
  const endpoint = (end: ReferenceEndPublic) => {
    const nodeId = graphIdOf(source.connectorId, end.connector_id, end.node_id)
    const rows = nodes.get(nodeId)?.rows ?? []
    return { nodeId, portIds: rows.some((row) => row.id === end.column) ? [end.column] : [] }
  }
  for (const reference of source.declared ?? []) {
    const [a, b] = reference.ends
    const from = endpoint(a)
    const to = endpoint(b)
    if (!nodes.has(from.nodeId) || !nodes.has(to.nodeId)) continue
    edges.push({
      id: JSON.stringify(["declared", reference.id]), label: "declared",
      source: from, target: to, directed: false, tone: "secondary",
      details: [
        { label: "Columns", value: `${a.node_label}.${a.column} ↔ ${b.node_label}.${b.column}` },
        { label: "Kind", value: "Declared reference: drawn by you, not kept by either source" },
      ],
    })
  }
  return { nodes: [...nodes.values()], edges, groups: [...groups].map(([id, label]) => ({ id, label })) }
}
