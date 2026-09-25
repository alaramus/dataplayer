import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceZ } from "d3-force-3d"

import type { GraphDocument, Point2, Point3 } from "./model"

const LINK_LENGTH = 245
const COLLISION_RADIUS = 105
const ITERATIONS = 260

interface LayoutNode extends Point3 {
  id: string
}

interface LayoutLink {
  source: string | LayoutNode
  target: string | LayoutNode
}

function hash(value: string): number {
  let result = 2166136261
  for (let index = 0; index < value.length; index++) {
    result ^= value.charCodeAt(index)
    result = Math.imul(result, 16777619)
  }
  return result >>> 0
}

export function arrange3(graph: GraphDocument, positions2: Record<string, Point2>): Record<string, Point3> {
  const ordered = [...graph.nodes].sort((a, b) => a.id.localeCompare(b.id))
  if (!ordered.length) return {}
  const xMiddle = (Math.min(...ordered.map((node) => positions2[node.id]!.x)) + Math.max(...ordered.map((node) => positions2[node.id]!.x))) / 2
  const zMiddle = (Math.min(...ordered.map((node) => positions2[node.id]!.y)) + Math.max(...ordered.map((node) => positions2[node.id]!.y))) / 2
  const nodes: LayoutNode[] = ordered.map((node) => {
    const seed = hash(node.id)
    const sketch = positions2[node.id]!
    return {
      id: node.id,
      x: (sketch.x - xMiddle) * 0.58,
      y: ((seed % 11) - 5) * 30,
      z: (sketch.y - zMiddle) * 0.58 + ((Math.floor(seed / 11) % 7) - 3) * 22,
    }
  })
  const ids = new Set(nodes.map((node) => node.id))
  const pairs = new Map<string, LayoutLink>()
  for (const edge of [...graph.edges].sort((a, b) => a.id.localeCompare(b.id))) {
    const source = edge.source.nodeId
    const target = edge.target.nodeId
    if (source === target || !ids.has(source) || !ids.has(target)) continue
    const pair = [source, target].sort()
    pairs.set(pair.join(":"), { source: pair[0]!, target: pair[1]! })
  }

  // D3 mutates its nodes and links. Keep that mutation inside this worker-owned
  // copy so the graph document and saved positions remain unchanged.
  const simulation = forceSimulation(nodes, 3)
    .force("links", forceLink<LayoutNode, LayoutLink>([...pairs.values()]).id((node) => node.id).distance(LINK_LENGTH).strength(0.35))
    .force("charge", forceManyBody<LayoutNode>().strength(-9500))
    .force("collisions", forceCollide<LayoutNode>(COLLISION_RADIUS).strength(1).iterations(3))
    .force("center", forceCenter(0, 0, 0))
    .force("sketch-x", forceX<LayoutNode>((node) => (positions2[node.id]!.x - xMiddle) * 0.58).strength(0.015))
    .force("sketch-z", forceZ<LayoutNode>((node) => (positions2[node.id]!.y - zMiddle) * 0.58).strength(0.015))
    .stop()
  for (let tick = 0; tick < ITERATIONS; tick++) simulation.tick()
  return Object.fromEntries(nodes.map((node) => [node.id, { x: node.x, y: node.y, z: node.z }]))
}

/** Recognize only the exact old projection; a manually moved node stays put. */
export function isLegacyFlat3(
  graph: GraphDocument,
  positions2: Record<string, Point2>,
  positions3: Record<string, Point3>,
): boolean {
  if (!graph.nodes.length) return false
  const groups = [...new Set(graph.nodes.map((node) => node.groupId ?? ""))].sort()
  return graph.nodes.every((node) => {
    const flat = positions2[node.id]
    const placed = positions3[node.id]
    if (!flat || !placed) return false
    return Math.abs(placed.x - flat.x * 0.7) < 0.000001 &&
      Math.abs(placed.y - groups.indexOf(node.groupId ?? "") * 180) < 0.000001 &&
      Math.abs(placed.z - flat.y * 0.55) < 0.000001
  })
}
