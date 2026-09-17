import type { Component, InjectionKey, Ref } from "vue"

import type { DropAdmission } from "./dropZone"
import type { DetachedPanel } from "./detached"
import type { DropZone, LayoutNode, NodeId, PanelId } from "./model"

/** What a panel shows of itself in a tab: nothing else about it is needed. */
export interface PanelLook {
  title: string
  icon: string
  /** #RRGGBB shared by this panel's tab and its floating title. */
  color?: string | null
  /** A quieter second line beside the title, given up first when narrow. */
  subtitle?: string
  /** Whether the tab offers a cross. Defaults to true. */
  closable?: boolean
  /** Hover text for the icon. Says nothing about whether it can be pressed. */
  iconTooltip?: string
  /**
   * Whether pressing the icon does something of its own. Defaults to false.
   *
   * Separate from the tooltip: while they were one field, an icon was drawn as
   * a button wherever it had hover text, and four kinds offered a press with
   * nothing behind it (D112).
   */
  iconCommand?: boolean
  /** What the panel's own reload button says. Absent: it offers none (D112). */
  reloadTooltip?: string
}

/**
 * A section on the bar at the foot of the screen: what it is called, and how
 * much is waiting in it.
 *
 * Named by its role rather than by its active tab: a column is a part of the
 * window, not a document, and a button whose word changed as the tab behind it
 * changed could not be aimed at twice.
 */
export interface AsideSection {
  id: NodeId
  title: string
  icon: string
  /** How many panels it holds, for the count beside the name. */
  panels: number
}

/**
 * The one thing the components of the engine are given.
 *
 * A panel is an id; what it looks like and what renders it are answered by
 * functions the feature supplied, which is what keeps the engine free of any
 * knowledge about the application (D12).
 */
export interface WorkspaceContext {
  tree: Ref<LayoutNode>
  panelIds: Ref<PanelId[]>
  /**
   * What to key a panel's rendering by, which is not its id: an id may be
   * renamed — a kept console becomes a document — and keying by it would
   * rebuild the panel and lose what is in it.
   */
  keyOf: (panelId: PanelId) => string
  detached: Ref<DetachedPanel[]>
  focusedDetached: Ref<PanelId | null>
  focusedLeaf: Ref<NodeId | null>
  dragging: Ref<PanelId | null>
  lookOf: (panelId: PanelId) => PanelLook
  componentOf: (panelId: PanelId) => Component
  /** What a pinned section shows while empty, keyed by the role it accepts. */
  emptyOf: (accepts: string | null) => Component | null
  /** What a collapsed section shows instead of its panel. Null: just a handle. */
  collapsedOf: (panelId: PanelId) => Component | null
  /**
   * What a whole section is called, keyed by the role it accepts.
   *
   * Only needed once a section can be off the screen: something has to name it
   * on the bar. Null where the feature has no name for that role, and a
   * section with no name cannot be put aside — there would be no way back.
   */
  sectionLookOf: (accepts: string | null) => { title: string; icon: string } | null
  /** The sections that are off the screen, in the order they were put aside. */
  aside: Ref<AsideSection[]>
  /**
   * What this section will take from the drag now in progress.
   *
   * Asked of the context rather than worked out by the section: the answer
   * needs the panel being dragged and the role the feature gave it, and a
   * section holds neither.
   */
  admissionOf: (leafId: NodeId) => DropAdmission
  activate: (panelId: PanelId) => void
  canDetach: (panelId: PanelId) => boolean
  detach: (panelId: PanelId) => void
  dock: (panelId: PanelId) => void
  /** Reached only from a look that sets `iconCommand`. */
  onIconClick?: (panelId: PanelId) => void
  close: (panelId: PanelId) => void
  /**
   * Close a panel unless it says it is not ready to go — what the cross does.
   *
   * `close` stays beside it because a layout operation the application
   * performs is not a person changing their mind (D66). Returns whether it
   * closed, so a floating frame honours the same refusal.
   */
  requestClose: (panelId: PanelId) => Promise<boolean>
  /** Close every panel of this section but the active one. */
  closeOthers: (leafId: NodeId) => Promise<void>
  focus: (leafId: NodeId) => void
  toggleCollapse: (leafId: NodeId) => void
  /** The first section in tree order, whose chevron the feature may own. */
  firstLeafId: Ref<NodeId | null>
  /**
   * Whether that chevron stays off: the feature's own chrome collapses the
   * first section, so the strip keeps its tabs and offers no second button
   * for the same gesture.
   */
  hideFirstCollapse: boolean
  /** Put a section on the bar, keeping everything in it. */
  putAside: (leafId: NodeId) => void
  /** Bring one back, into the column it was in. */
  bringBack: (leafId: NodeId) => void
  resize: (
    splitId: NodeId,
    beforeIndex: number,
    afterIndex: number,
    delta: number,
    minPercent: number
  ) => void
  /** A tab was pressed. Not yet a drag: see `pointerMoved`. */
  press: (panelId: PanelId, x: number, y: number) => void
  /**
   * The pointer moved, wherever it is. A press becomes a drag here, held by
   * the engine and not by the section the tab came from — the pointer leaves
   * that section in the first moment of the gesture.
   */
  pointerMoved: (x: number, y: number) => void
  /** `at` is the place in the target strip, meaningful only for "beside". */
  endDrag: (targetLeafId: NodeId | null, zone: DropZone | null, at?: number) => void
}

export const workspaceKey: InjectionKey<WorkspaceContext> = Symbol("workspace")
