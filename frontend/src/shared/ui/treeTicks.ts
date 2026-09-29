/**
 * The ticks of a tree whose ticks are its leaves: a branch is ticked when
 * every leaf under it is, half-ticked when only some are, and ticking it ticks
 * them all.
 *
 * Quasar's tree knows this rule, but only for the tick box it draws itself,
 * and that box cannot be the kit's; so AppTree draws AppCheckbox and asks
 * here instead.
 */

export interface TickNode {
  children?: readonly TickNode[]
  lazy?: boolean
  [key: string]: unknown
}

/** Ticked, empty, or "some of them" (null). */
export type TickState = boolean | null

/**
 * Every leaf a tick on this node stands for.
 *
 * A branch that has not been read yet has none: what is under it is not known,
 * and a tick on it would stand for nothing.
 */
export function leafKeys(node: TickNode, nodeKey: string): string[] {
  const children = node.children ?? []
  if (children.length > 0) return children.flatMap((child) => leafKeys(child, nodeKey))
  if (node.lazy === true) return []
  return [String(node[nodeKey])]
}

/**
 * The box of every node, in one walk of the tree. A node with no leaf under
 * it is absent: it gets no box at all.
 */
export function tickStates(
  nodes: readonly TickNode[],
  nodeKey: string,
  ticked: readonly string[]
): Map<string, TickState> {
  const on = new Set(ticked)
  const states = new Map<string, TickState>()
  const walk = (node: TickNode): { leaves: number; ticked: number } => {
    const children = node.children ?? []
    let count = { leaves: 0, ticked: 0 }
    if (children.length > 0) {
      for (const child of children) {
        const below = walk(child)
        count = { leaves: count.leaves + below.leaves, ticked: count.ticked + below.ticked }
      }
    } else if (node.lazy !== true) {
      count = { leaves: 1, ticked: on.has(String(node[nodeKey])) ? 1 : 0 }
    }
    if (count.leaves > 0) {
      const some = count.ticked > 0 ? null : false
      states.set(String(node[nodeKey]), count.ticked === count.leaves ? true : some)
    }
    return count
  }
  nodes.forEach(walk)
  return states
}

/** The ticks after a node's leaves are ticked or unticked; the rest stay as they were. */
export function withTicks(ticked: readonly string[], leaves: readonly string[], on: boolean): string[] {
  if (!on) return ticked.filter((key) => !leaves.includes(key))
  return [...ticked, ...leaves.filter((key) => !ticked.includes(key))]
}
