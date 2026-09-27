import type { CatalogNode, DeclaredReferencePublic, ReferenceEndPublic, RelationModel } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { GRAPH_LIMITS } from "@/shared/graph/model"
import { MAX_RELATIONS } from "./model"
import type { DiagramNodeRef, FarRelation, RelationGraphSource } from "./model"

/** Messages authored here are safe to display, unlike arbitrary driver errors. */
export class GraphLoadError extends Error {}

/**
 * The selection with every node that holds relations replaced by those
 * directly inside it, grouped under its name: a workbook becomes its sheets. One
 * that cannot be listed stays as it was and fails where a read would.
 */
export async function expandHolders(
  requested: DiagramNodeRef[],
  list: (nodeId: string) => Promise<CatalogNode[]>,
): Promise<DiagramNodeRef[]> {
  const expanded: DiagramNodeRef[] = []
  for (const node of requested) {
    if (node.holdsNodes !== true) {
      expanded.push(node)
      continue
    }
    try {
      for (const child of await list(node.id)) {
        if (child.describable === true) expanded.push({ id: child.id, label: child.name, group: node.label })
      }
    } catch {
      expanded.push({ id: node.id, label: node.label })
    }
  }
  return expanded
}

/**
 * The declared references with an end among the relations read, and the
 * relations at their far ends that were not, each read from its own
 * connection (D106). A far end that cannot be read is drawn as a placeholder
 * named as the reference named it.
 */
export async function withDeclared(
  source: RelationGraphSource,
  connectorId: string,
  references: DeclaredReferencePublic[],
  read: (end: ReferenceEndPublic, signal: AbortSignal) => Promise<RelationModel>,
  signal: AbortSignal,
): Promise<RelationGraphSource> {
  const here = new Set(source.models.map((model) => model.node_id))
  const isHere = (end: ReferenceEndPublic) => end.connector_id === connectorId && here.has(end.node_id)
  const declared = references.filter((reference) => reference.ends.some(isHere))
  const wanted = new Map<string, ReferenceEndPublic>()
  for (const end of declared.flatMap((reference) => reference.ends)) {
    if (!isHere(end)) wanted.set(JSON.stringify([end.connector_id, end.node_id]), end)
  }
  const far: FarRelation[] = []
  for (const end of wanted.values()) {
    signal.throwIfAborted()
    const place = { connectorId: end.connector_id, connectorName: end.connector_name, adapterType: end.adapter_type, nodeId: end.node_id, label: end.node_label }
    try {
      far.push({ ...place, model: await read(end, signal) })
    } catch (error) {
      signal.throwIfAborted()
      far.push({ ...place, model: null, message: messageOf(error, "Could not read this structure") })
    }
  }
  return { ...source, connectorId, declared, far }
}

export async function loadRelations(
  requested: DiagramNodeRef[],
  read: (nodeId: string, signal: AbortSignal) => Promise<RelationModel>,
  signal: AbortSignal,
  progress: (loaded: number) => void,
): Promise<RelationGraphSource> {
  if (requested.length > MAX_RELATIONS) throw new GraphLoadError(`Select at most ${MAX_RELATIONS} tables for one diagram.`)
  const stop = new AbortController()
  const combined = AbortSignal.any([signal, stop.signal])
  const result: RelationGraphSource = { requested, models: [], failures: [] }
  let next = 0
  let loaded = 0
  let rows = 0
  let edges = 0
  let tooLarge = false
  async function work() {
    while (next < requested.length) {
      combined.throwIfAborted()
      const item = requested[next++]!
      try {
        const model = await read(item.id, combined)
        combined.throwIfAborted()
        rows += model.columns?.length ?? 0
        edges += model.constraints?.filter((key) => key.kind === "foreign_key").length ?? 0
        if (rows > GRAPH_LIMITS.rows || edges > GRAPH_LIMITS.edges) {
          tooLarge = true
          stop.abort()
          throw new GraphLoadError("This graph is too large. Select fewer tables.")
        }
        result.models.push(model)
      } catch (error) {
        if (tooLarge) throw new GraphLoadError("This graph is too large. Select fewer tables.")
        combined.throwIfAborted()
        result.failures.push({ ...item, message: messageOf(error, "Could not read this structure") })
      }
      progress(++loaded)
    }
  }
  try {
    await Promise.all(Array.from({ length: Math.min(4, requested.length) }, () => work()))
    result.models.sort((a, b) => a.node_id.localeCompare(b.node_id))
    return result
  } finally { stop.abort() }
}
