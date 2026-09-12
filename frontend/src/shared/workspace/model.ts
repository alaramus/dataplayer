/**
 * The layout of the workspace: a tree of sections, and nothing about what
 * they show.
 *
 * A panel is referred to by id only. What a panel is belongs to the feature
 * that uses the engine — see docs/decisions/2026-08-22-workspace-design.md.
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
  /** Null only in a pinned section that holds nothing. */
  activePanel: PanelId | null
  collapsed: boolean
  /**
   * The role of panel that lands here by default.
   *
   * An opaque string, compared and never parsed: what roles exist is the
   * business of the feature. Without it a section that holds nothing could
   * not be a destination, because placement reads the panels a section holds.
   * See the spec, T1.
   */
  accepts?: string
  /**
   * A section that stays on screen with nothing in it.
   *
   * The one thing that holds up "the three columns are always there": every
   * other rule would let the last panel take its section with it.
   */
  pinned?: boolean
  /**
   * A section put aside into the bar at the foot of the screen.
   *
   * Not `collapsed` narrowed to nothing: a collapsed column is still a column
   * — forty pixels of handle, and whatever the feature draws in them — while
   * a section put aside is off the screen altogether and reachable only from
   * the bar, the way a window put aside is (D92). A column with nothing to
   * show at that width was drawn as an empty strip, which is a column that
   * costs room and says nothing.
   */
  minimized?: boolean
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

/**
 * What a collapsed section leaves behind.
 *
 * Enough for the handle, and for the strip of icons a feature may put under
 * it: a column pushed aside is still a way back to what is in it.
 */
export const COLLAPSED_PX = 40

/**
 * Movement under this much reads as a press rather than as the start of a
 * drag. One number for the border between two columns and for a tab, because
 * it answers one question — did the hand mean to move this? See G1.
 */
export const PRESS_THRESHOLD_PX = 3

export interface LeafOptions {
  activePanel?: PanelId
  accepts?: string
  pinned?: boolean
}

export function makeLeaf(id: NodeId, panels: PanelId[], options: LeafOptions = {}): LeafNode {
  const [first] = panels
  // A section with nothing in it is a state normalize() repairs, not one to
  // build - unless it is pinned, where emptiness is the whole point: a column
  // exists before anything has been opened in it.
  if (first === undefined && options.pinned !== true) {
    throw new Error(`A leaf needs at least one panel: ${id}`)
  }
  const leaf: LeafNode = {
    kind: "leaf",
    id,
    panels,
    activePanel: options.activePanel ?? first ?? null,
    collapsed: false,
  }
  if (options.accepts !== undefined) leaf.accepts = options.accepts
  if (options.pinned === true) leaf.pinned = true
  return leaf
}

export function makeSplit(
  id: NodeId,
  direction: Direction,
  children: LayoutNode[],
  sizes: number[]
): SplitNode {
  return { kind: "split", id, direction, children, sizes }
}

/** A restored layout can contain ids from an earlier browser session. */
export function nextId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}
