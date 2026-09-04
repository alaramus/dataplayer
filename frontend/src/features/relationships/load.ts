import type { RelationModel } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { GRAPH_LIMITS } from "@/shared/graph/model"
import { MAX_RELATIONS } from "./model"
import type { DiagramNodeRef, RelationGraphSource } from "./model"

/** Messages authored here are safe to display, unlike arbitrary driver errors. */
export class GraphLoadError extends Error {}

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
