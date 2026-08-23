import type { Component, InjectionKey, Ref } from "vue"

import type { DropZone, LayoutNode, NodeId, PanelId } from "./model"

/** What a panel shows of itself in a tab: nothing else about it is needed. */
export interface PanelLook {
  title: string
  icon: string
  /**
   * Whether the tab offers a cross. Defaults to true.
   *
   * A property of the panel rather than of the section: tabs close in the
   * pinned column of data just as they do anywhere, while the panel of
   * connections has no parameters and nothing to say once closed. See T3.
   */
  closable?: boolean
}

/**
 * The one thing the components of the engine are given.
 *
 * The type of a panel does not appear here: a panel is an id, and what it
 * looks like and which component renders it are answered by two functions the
 * feature supplied. That is what keeps the engine free of any knowledge about
 * the application. See the spec, W1.
 */
export interface WorkspaceContext {
  tree: Ref<LayoutNode>
  focusedLeaf: Ref<NodeId | null>
  dragging: Ref<PanelId | null>
  lookOf: (panelId: PanelId) => PanelLook
  componentOf: (panelId: PanelId) => Component
  /**
   * What a pinned section shows while it holds nothing.
   *
   * The engine knows the section is empty; what to write there is application
   * knowledge, so it arrives keyed by the role the section accepts.
   */
  emptyOf: (accepts: string | null) => Component | null
  /**
   * What a collapsed section shows in place of its panel, if anything.
   *
   * The engine knows the section is narrow; what is worth keeping at that
   * width is application knowledge, so it is asked for by panel. Null leaves
   * the handle alone, which is what a section with nothing to show wants.
   */
  collapsedOf: (panelId: PanelId) => Component | null
  activate: (panelId: PanelId) => void
  close: (panelId: PanelId) => void
  /**
   * Close every panel of this section but the active one.
   *
   * A layout operation and so the engine's: what a panel is has no bearing on
   * it. A panel the feature says cannot be closed stays, exactly as it does
   * when its own cross is asked for and there is none.
   */
  closeOthers: (leafId: NodeId) => void
  focus: (leafId: NodeId) => void
  toggleCollapse: (leafId: NodeId) => void
  resize: (splitId: NodeId, index: number, delta: number, minPercent: number) => void
  startDrag: (panelId: PanelId) => void
  endDrag: (targetLeafId: NodeId | null, zone: DropZone | null) => void
}

export const workspaceKey: InjectionKey<WorkspaceContext> = Symbol("workspace")
