import type { Component, InjectionKey, Ref } from "vue"

import type { DropZone, LayoutNode, NodeId, PanelId } from "./model"

/** What a panel shows of itself in a tab: nothing else about it is needed. */
export interface PanelLook {
  title: string
  icon: string
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
  activate: (panelId: PanelId) => void
  close: (panelId: PanelId) => void
  focus: (leafId: NodeId) => void
  toggleCollapse: (leafId: NodeId) => void
  resize: (splitId: NodeId, index: number, delta: number, minPercent: number) => void
  startDrag: (panelId: PanelId) => void
  endDrag: (targetLeafId: NodeId | null, zone: DropZone | null) => void
}

export const workspaceKey: InjectionKey<WorkspaceContext> = Symbol("workspace")
