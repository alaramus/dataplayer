/**
 * The layout of the workspace: a tree of sections, and nothing about what
 * they show.
 *
 * A panel is referred to by id only. What a panel is belongs to the feature
 * that uses the engine — see docs/superpowers/specs/2026-08-22-workspace-design.md.
 */

export type PanelId = string
export type NodeId = string

/** The position of a node: the index to take at every level from the root. */
export type Path = number[]

export type Direction = "row" | "column"

/** Where a dragged panel would land, relative to the section under it. */
export type DropZone = "left" | "right" | "top" | "bottom" | "center"

export interface LeafNode {
  kind: "leaf"
  id: NodeId
  panels: PanelId[]
  activePanel: PanelId
  collapsed: boolean
}

export interface SplitNode {
  kind: "split"
  id: NodeId
  direction: Direction
  children: LayoutNode[]
  /** Percentages, one per child, summing to 100. */
  sizes: number[]
}

export type LayoutNode = SplitNode | LeafNode

/** The smallest a section may be dragged to. Percentages cannot say this. */
export const MIN_PANEL_PX = 120

/** What a collapsed section leaves behind: enough for the handle and no more. */
export const COLLAPSED_PX = 28

export function makeLeaf(id: NodeId, panels: PanelId[], activePanel?: PanelId): LeafNode {
  return {
    kind: "leaf",
    id,
    panels,
    activePanel: activePanel ?? panels[0],
    collapsed: false,
  }
}

export function makeSplit(
  id: NodeId,
  direction: Direction,
  children: LayoutNode[],
  sizes: number[]
): SplitNode {
  return { kind: "split", id, direction, children, sizes }
}

let counter = 0

/** Ids are only ever compared, never parsed, so a counter is enough. */
export function nextId(prefix: string): string {
  counter += 1
  return `${prefix}-${String(counter)}`
}
