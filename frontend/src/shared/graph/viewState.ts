import { z } from "zod"

import { GRAPH_LIMITS } from "./model"
import type { GraphViewState } from "./model"

const coordinate = z.number().finite().min(-10_000_000).max(10_000_000)
const point2 = z.object({ x: coordinate, y: coordinate })
const point3 = point2.extend({ z: coordinate })
const stateSchema = z.object({
  mode: z.enum(["2d", "3d"]),
  positions2: z.record(z.string(), point2).refine((value) => Object.keys(value).length <= GRAPH_LIMITS.nodes),
  positions3: z.record(z.string(), point3).refine((value) => Object.keys(value).length <= GRAPH_LIMITS.nodes),
  camera2: point2.extend({ zoom: z.number().finite().min(0.03).max(3) }).nullable(),
  camera3: z.object({ position: point3, target: point3 }).refine(({ position, target }) =>
    Math.hypot(position.x - target.x, position.y - target.y, position.z - target.z) >= 1
  ).nullable(),
  expanded: z.boolean(),
  labels: z.boolean(),
  groupId: z.string().max(2048).nullable(),
})

export const emptyGraphView = (): GraphViewState => ({
  mode: "2d", positions2: {}, positions3: {}, camera2: null, camera3: null,
  expanded: true, labels: true, groupId: null,
})

export function parseGraphView(raw: string | null): GraphViewState | null {
  if (!raw || raw.length > 200_000) return null
  try {
    const parsed = z.object({ version: z.literal(1), state: stateSchema }).safeParse(JSON.parse(raw))
    return parsed.success ? parsed.data.state : null
  } catch { return null }
}

export function serializeGraphView(state: GraphViewState): string {
  return JSON.stringify({ version: 1, state: stateSchema.parse(state) })
}
