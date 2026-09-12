/**
 * A workspace of resizable sections holding panels.
 *
 * The engine knows nothing about what a panel shows: a feature supplies the
 * panel type, a component per panel and a look per panel, and gets a layout
 * that can be resized, collapsed, tabbed and rearranged.
 */
export { default as WorkspaceRoot } from "./WorkspaceRoot.vue"
export { default as WorkspaceDetachTarget } from "./WorkspaceDetachTarget.vue"
export { default as WorkspaceTaskbar } from "./WorkspaceTaskbar.vue"
export { useWorkspace, workspaceKey } from "./useWorkspace"
export type {
  OpenOptions,
  RestoreOutcome,
  PanelLook,
  WorkspaceApi,
  WorkspaceContext,
  WorkspaceOptions,
} from "./useWorkspace"
export { COLLAPSED_PX, makeLeaf, makeSplit, MIN_PANEL_PX, nextId } from "./model"
export { leavesOf } from "./tree"
export type {
  DropZone,
  LayoutNode,
  LeafNode,
  LeafOptions,
  NodeId,
  PanelId,
  SplitNode,
} from "./model"
