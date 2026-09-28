import { z } from "zod"
import type { ZodType } from "zod"

import type { LayoutNode, PanelId } from "./model"
import { leavesOf, removePanel } from "./tree"

/**
 * A stored layout is untrusted input, like anything else that comes from
 * outside. It is parsed, cross-checked, and refused whole: half a restored
 * tree is worse than the default one. See the spec, W9.
 */

/**
 * 2: sections gained a role and the right to stay empty. A layout written
 * before that is one section holding everything, so restoring it would leave
 * the user without the columns the screen now promises.
 *
 * 3: a data tab carries the connection it came from, so that it can say whose
 * it is and draw the icon of its source before the list of connections has
 * been read. A layout written under 2 holds tabs that cannot. Refused whole,
 * like any other foreign version — see the spec, T6 and P8.
 */
export const WORKSPACE_VERSION = 3

const leafSchema = z.object({
  kind: z.literal("leaf"),
  id: z.string(),
  panels: z.array(z.string()),
  activePanel: z.string().nullable(),
  collapsed: z.boolean(),
  accepts: z.string().optional(),
  pinned: z.boolean().optional(),
  // Optional, so a layout written before sections could be put aside is still
  // a layout: every field added to a stored section is optional, or the next
  // one refuses every tree anybody already has.
  minimized: z.boolean().optional(),
})

const nodeSchema: ZodType<LayoutNode> = z.lazy(() =>
  z.union([
    leafSchema,
    z.object({
      kind: z.literal("split"),
      id: z.string(),
      direction: z.union([z.literal("row"), z.literal("column")]),
      children: z.array(nodeSchema).min(2),
      sizes: z.array(z.number().finite().nonnegative()).min(2),
    }),
  ])
)

export function serializeWorkspace<P>(tree: LayoutNode, panels: P[]): string {
  return JSON.stringify({ version: WORKSPACE_VERSION, tree, panels })
}

/**
 * Whether a stored panel is of a kind the application no longer has. Such a
 * panel is dropped with its place in the tree rather than refusing the whole
 * layout: the application said it went away, so it is not damage.
 */
export type RetiredPanel = (panel: unknown) => boolean

export function parseWorkspace<P extends { id: string }>(
  raw: string | null,
  panelSchema: ZodType<P>,
  retired?: RetiredPanel
): { tree: LayoutNode; panels: P[] } | null {
  if (raw === null) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }

  const envelope = z
    .object({
      version: z.literal(WORKSPACE_VERSION),
      tree: nodeSchema,
      panels: z.array(z.unknown()),
    })
    .safeParse(parsed)
  if (!envelope.success) return null
  if (!sizesMatchChildren(envelope.data.tree)) return null

  let tree: LayoutNode | null = envelope.data.tree
  const kept: unknown[] = []
  for (const panel of envelope.data.panels) {
    const id = typeof panel === "object" && panel !== null ? (panel as { id?: unknown }).id : undefined
    if (retired?.(panel) === true && typeof id === "string") {
      tree = removePanel(tree, id)
      if (tree === null) return null
    } else {
      kept.push(panel)
    }
  }
  const checked = z.array(panelSchema).safeParse(kept)
  if (!checked.success) return null
  const panels = checked.data

  const known = new Set<PanelId>(panels.map((panel) => panel.id))
  if (known.size !== panels.length) return null
  const placed = new Set<PanelId>()
  const nodeIds = new Set<string>()
  function uniqueNodes(node: LayoutNode): boolean {
    if (nodeIds.has(node.id)) return false
    nodeIds.add(node.id)
    return node.kind === "leaf" || node.children.every(uniqueNodes)
  }
  if (!uniqueNodes(tree)) return null
  for (const leaf of leavesOf(tree)) {
    if (!leaf.panels.every((id) => known.has(id))) return null
    for (const id of leaf.panels) {
      if (placed.has(id)) return null
      placed.add(id)
    }
    // Emptiness is allowed to a pinned section and to nothing else, and it is
    // the only case in which nothing is active. The two are checked together
    // so that neither can be restored without the other.
    if (leaf.panels.length === 0) {
      if (leaf.pinned !== true || leaf.activePanel !== null) return null
      continue
    }
    if (leaf.activePanel === null || !leaf.panels.includes(leaf.activePanel)) return null
  }
  if (placed.size !== known.size) return null

  return { tree, panels }
}

function sizesMatchChildren(node: LayoutNode): boolean {
  if (node.kind === "leaf") return true
  if (node.sizes.length !== node.children.length) return false
  if (Math.abs(node.sizes.reduce((sum, size) => sum + size, 0) - 100) > 0.001) return false
  return node.children.every(sizesMatchChildren)
}
