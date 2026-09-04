import type { Component, InjectionKey, Ref } from "vue"

import type { DropAdmission } from "./dropZone"
import type { DetachedPanel } from "./detached"
import type { DropZone, LayoutNode, NodeId, PanelId } from "./model"

/** What a panel shows of itself in a tab: nothing else about it is needed. */
export interface PanelLook {
  title: string
  icon: string
  /** Optional #RRGGBB background shared by this panel's tab and floating title. */
  color?: string | null
  /**
   * A quieter second line beside the title: whose panel this is.
   *
   * Beside rather than in front, and the first thing to be given up when the
   * tab is narrow: the title is what the eye looks for. See P8.
   */
  subtitle?: string
  /**
   * Whether the tab offers a cross. Defaults to true.
   *
   * A property of the panel rather than of the section: tabs close in the
   * pinned column of data just as they do anywhere, while the panel of
   * connections has no parameters and nothing to say once closed. See T3.
   */
  closable?: boolean
  /**
   * What the icon says when hovered, if clicking it does something of its
   * own rather than activating the tab.
   *
   * Absent means the icon is inert: the catalog carries "Edit connection"
   * here and a data tab carries nothing, so the engine knows which tabs
   * have an actionable icon without knowing what a catalog is. See T5.
   */
  iconTooltip?: string
  /**
   * What the reload button says when hovered, if the panel offers one.
   *
   * Present means the tab draws the button; absent means it does not. The same
   * pairing as `iconTooltip`: the engine learns that a tab has something to
   * re-read without learning what a catalog is.
   */
  reloadTooltip?: string
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
  panelIds: Ref<PanelId[]>
  detached: Ref<DetachedPanel[]>
  focusedDetached: Ref<PanelId | null>
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
  /**
   * What this section will take from the drag now in progress.
   *
   * Asked of the context rather than worked out by the section, because the
   * answer needs the panel being dragged and the role the feature gave it —
   * neither of which a section holds. See P1.
   */
  admissionOf: (leafId: NodeId) => DropAdmission
  activate: (panelId: PanelId) => void
  canDetach: (panelId: PanelId) => boolean
  detach: (panelId: PanelId) => void
  dock: (panelId: PanelId) => void
  /**
   * What a click on the icon of a tab does, if the feature says it does
   * anything at all rather than activating the tab.
   *
   * Asked of the context rather than worked out by the section, because the
   * answer needs the panel being clicked and what the feature wants to do
   * with it - for a catalog that is opening the edit window, for data it is
   * nothing. The engine knows the tab, not what a catalog is. See T5.
   */
  onIconClick?: (panelId: PanelId) => void
  /**
   * Re-read a panel, without making it the one on show.
   *
   * What re-reading means belongs to the panel — a list re-fetches, a catalog
   * re-reads the level it stands on, a grid re-runs its page — so the engine
   * asks and does not know. Awaited, so the button can say it is working.
   */
  onReload?: (panelId: PanelId) => Promise<void> | void
  close: (panelId: PanelId) => void
  /**
   * Close a panel unless it says it is not ready to go.
   *
   * What the cross on a tab does. `close` stays as it is, because a layout
   * operation the application itself performs — replacing a renamed panel,
   * clearing a strip — is not a person changing their mind (D66).
   * Returns whether it closed, so a floating frame honours the same refusal.
   */
  requestClose: (panelId: PanelId) => Promise<boolean>
  /**
   * Close every panel of this section but the active one.
   *
   * A layout operation and so the engine's: what a panel is has no bearing on
   * it. A panel the feature says cannot be closed stays, exactly as it does
   * when its own cross is asked for and there is none.
   */
  closeOthers: (leafId: NodeId) => Promise<void>
  focus: (leafId: NodeId) => void
  toggleCollapse: (leafId: NodeId) => void
  resize: (
    splitId: NodeId,
    beforeIndex: number,
    afterIndex: number,
    delta: number,
    minPercent: number
  ) => void
  /**
   * A tab was pressed. Not yet a drag: see `pointerMoved`.
   */
  press: (panelId: PanelId, x: number, y: number) => void
  /**
   * The pointer moved, wherever it is.
   *
   * A press becomes a drag here, once the hand has moved far enough to mean
   * it. Held by the engine rather than by the section the tab came from: the
   * pointer leaves that section in the first moment of the gesture. See G1.
   */
  pointerMoved: (x: number, y: number) => void
  /**
   * Let go. `at` is the place in the target strip a tab was aimed at, and is
   * meaningful only for the zone that means "beside the others".
   */
  endDrag: (targetLeafId: NodeId | null, zone: DropZone | null, at?: number) => void
}

export const workspaceKey: InjectionKey<WorkspaceContext> = Symbol("workspace")
