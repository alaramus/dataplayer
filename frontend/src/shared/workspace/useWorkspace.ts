import { computed, ref, watch } from "vue"
import type { Component, Ref } from "vue"
import type { ZodType } from "zod"

import { workspaceKey } from "./context"
import type { AsideSection, PanelLook, WorkspaceContext } from "./context"
import { dockedLayout, returnPanel } from "./detached"
import type { DetachedPanel } from "./detached"
import { admittedZone } from "./dropZone"
import type { DropAdmission } from "./dropZone"
import { nextId, PRESS_THRESHOLD_PX } from "./model"
import type { LayoutNode, NodeId, PanelId } from "./model"
import { parseWorkspace, serializeWorkspace } from "./persist"
import { leafForKind } from "./placement"
import {
  activatePanel,
  addPanel,
  leavesOf,
  movePanel,
  removePanel,
  renamePanel,
  resizeSplit,
  setCollapsed,
  setMinimized,
} from "./tree"

export { workspaceKey }
export type { PanelLook, WorkspaceContext }

export interface WorkspaceOptions<P extends { id: string }> {
  storageKey: string
  panelSchema: ZodType<P>
  defaults: () => { tree: LayoutNode; panels: P[] }
  kindOf: (panel: P) => string
  look: (panel: P) => PanelLook
  /**
   * What renders a panel, and the key to remember it under.
   *
   * Must answer with the same component for the same key: a tab that is not
   * showing is kept alive, and Vue tells two components apart by identity, so
   * a component built afresh on each call is a different one each time. The
   * key and not the panel's id, because an id may be renamed and a rename must
   * not rebuild the panel.
   */
  component: (panel: P, key: string) => Component
  /** What a pinned section shows while empty, by the role it accepts. */
  empty?: (accepts: string | null) => Component | null
  /**
   * What a collapsed section shows instead of its panel.
   *
   * Same requirement as `component`: the same component for the same panel,
   * or every render replaces it.
   */
  collapsed?: (panel: P) => Component | null
  /**
   * What a whole section is called, by the role it accepts.
   *
   * The one thing the engine needs in words about a role, and only because a
   * section put aside has to be named on the bar at the foot of the screen. A
   * role with no name here is a section that cannot be put aside.
   */
  sectionLook?: (accepts: string | null) => { title: string; icon: string } | null
  /**
   * What a click on the icon of a tab does, if anything.
   *
   * Reached only from a look that sets `iconCommand`: an icon with a tooltip
   * and no command behind it is drawn as plain hover text (D112).
   */
  onIconClick?: (panel: P) => void
  /**
   * Whether a panel may be closed now.
   *
   * Asked the way reloading is asked: the engine knows a tab is going, and
   * what that costs belongs to the feature. Nothing said means yes.
   */
  beforeClose?: (panelId: PanelId) => Promise<boolean> | boolean
  /**
   * Whether the first section keeps no collapse chevron of its own: the
   * feature's own chrome — the application header — collapses it, so a
   * second button for the same gesture would only double it. Off unless
   * asked: the demo and the tests keep the handle.
   */
  hideFirstCollapse?: boolean
}

/** How an opened panel treats the ones already there. */
export interface OpenOptions {
  /**
   * Close every other panel of the same kind first.
   *
   * What makes the middle column hold one catalog: the rule is stated at the
   * call site rather than built into the engine, so allowing two later is
   * dropping the flag. See the spec, T4.
   */
  replace?: boolean
}

export interface WorkspaceApi<P extends { id: string }> {
  context: WorkspaceContext
  panels: Ref<P[]>
  open: (panel: P, options?: OpenOptions) => void
  replace: (oldPanelId: string, panel: P) => void
  snapshot: () => string
  restore: (snapshot: string) => Promise<RestoreOutcome>
  reset: () => void
}

export type RestoreOutcome = "restored" | "cancelled" | "changed" | "invalid"

export function useWorkspace<P extends { id: string }>(
  options: WorkspaceOptions<P>
): WorkspaceApi<P> {
  const restored = parseWorkspace(localStorage.getItem(options.storageKey), options.panelSchema)
  const start = restored ?? options.defaults()

  // ref() rewrites a union into its own unwrapped shape, so the type is
  // restated: without this the discriminant on tree.value stops narrowing and
  // every kind check downstream fails to compile.
  const tree = ref<LayoutNode>(start.tree) as Ref<LayoutNode>
  const panels = ref<P[]>(start.panels) as Ref<P[]>
  const focusedLeaf = ref<NodeId | null>(null)
  const dragging = ref<PanelId | null>(null)
  const detached = ref<DetachedPanel[]>([])
  const focusedDetached = ref<PanelId | null>(null)

  // Not a ref: nothing renders from it, and a press that never becomes a drag
  // must not make the screen do anything at all.
  let pressed: { panelId: PanelId; x: number; y: number } | null = null

  /**
   * What the render keys a panel by, which its id is not.
   *
   * A panel is allowed to be renamed: a console that somebody keeps becomes a
   * document and its id says so. Keyed by the id, that rename would throw the
   * instance away — the results in it, a half-answered parameter, an open
   * transaction — which is the opposite of what a rename means. Not a ref: it
   * is read while rendering and changes nothing on screen by itself.
   */
  const renderKeys = new Map<PanelId, string>()
  let keys = 0

  function keyOf(panelId: PanelId): string {
    const known = renderKeys.get(panelId)
    if (known !== undefined) return known
    keys += 1
    const fresh = `k${keys}`
    renderKeys.set(panelId, fresh)
    return fresh
  }

  /** Forget the panels that are gone, so a session does not accumulate keys. */
  function pruneKeys() {
    const live = new Set(panels.value.map((panel) => panel.id))
    for (const panelId of [...renderKeys.keys()]) {
      if (!live.has(panelId)) renderKeys.delete(panelId)
    }
  }

  const panelOf = (panelId: PanelId): P | undefined =>
    panels.value.find((panel) => panel.id === panelId)

  // Vue's default flush coalesces every change made in one tick into a single
  // write. flush: "sync" would put a synchronous localStorage write on every
  // frame of a border drag, which is a price the user pays so that a test can
  // skip an await.
  watch(
    [tree, panels, detached],
    () => {
      localStorage.setItem(options.storageKey, serializeWorkspace(dockedLayout(tree.value, detached.value), panels.value))
    },
    { deep: true }
  )

  function open(panel: P, { replace = false }: OpenOptions = {}) {
    if (panelOf(panel.id) !== undefined) {
      activate(panel.id)
      return
    }
    if (replace) {
      const kind = options.kindOf(panel)
      for (const other of panels.value.filter((one) => options.kindOf(one) === kind)) {
        close(other.id)
      }
    }
    const target = leafForKind(
      tree.value,
      (panelId) => {
        const found = panelOf(panelId)
        return found === undefined ? null : options.kindOf(found)
      },
      options.kindOf(panel),
      focusedLeaf.value
    )
    if (target === null) return
    panels.value = [...panels.value, panel]
    tree.value = addPanel(tree.value, target, panel.id)
  }

  function replace(oldPanelId: string, panel: P) {
    if (panels.value.every((candidate) => candidate.id !== oldPanelId)) return
    if (panel.id !== oldPanelId && panelOf(panel.id) !== undefined) {
      close(panel.id)
    }
    const index = panels.value.findIndex((candidate) => candidate.id === oldPanelId)
    if (index < 0) return
    // The key travels with the panel, so this reads as a rename rather than as
    // one panel closing and another opening in its place.
    if (panel.id !== oldPanelId) {
      const key = renderKeys.get(oldPanelId)
      renderKeys.delete(oldPanelId)
      if (key !== undefined) renderKeys.set(panel.id, key)
    }
    // Written into the panel that is already there rather than put in its
    // place. What renders a panel was handed that object and reads its fields
    // as it draws, so swapping in another one leaves the panel describing
    // itself as it used to be — the console that was kept would go on calling
    // itself a draft.
    const existing = panels.value[index]! as P & Record<string, unknown>
    for (const field of Object.keys(existing)) {
      if (!(field in panel)) delete existing[field]
    }
    Object.assign(existing, panel)
    tree.value = renamePanel(tree.value, oldPanelId, panel.id)
    detached.value = detached.value.map((entry) => entry.panelId === oldPanelId
      ? { ...entry, panelId: panel.id, accepts: options.kindOf(panel) }
      : entry)
    if (focusedDetached.value === oldPanelId) focusedDetached.value = panel.id
  }

  function close(panelId: PanelId) {
    const without = removePanel(tree.value, panelId)
    // The workspace never empties: a screen with no sections at all offers the
    // user nothing to act on and no way back. removePanel answers null for
    // exactly that case, so the rule needs no second guard counting panels -
    // one that could never disagree, and so could never be seen to work.
    if (without === null) return
    tree.value = without
    panels.value = panels.value.filter((panel) => panel.id !== panelId)
    renderKeys.delete(panelId)
    detached.value = detached.value.filter((entry) => entry.panelId !== panelId)
    if (focusedDetached.value === panelId) focusedDetached.value = null
  }

  function activate(panelId: PanelId) {
    if (detached.value.some((entry) => entry.panelId === panelId)) {
      focusedDetached.value = panelId
      return
    }
    focusedDetached.value = null
    tree.value = activatePanel(tree.value, panelId)
  }

  function canDetach(panelId: PanelId): boolean {
    return panelOf(panelId) !== undefined && lookOf(panelId).closable !== false &&
      leavesOf(tree.value).some((leaf) => leaf.panels.includes(panelId)) &&
      removePanel(tree.value, panelId) !== null
  }

  function detach(panelId: PanelId) {
    if (!canDetach(panelId)) return
    const leaf = leavesOf(tree.value).find((one) => one.panels.includes(panelId))
    const panel = panelOf(panelId)
    const without = removePanel(tree.value, panelId)
    if (leaf === undefined || panel === undefined || without === null) return
    context.endDrag(null, null)
    detached.value = [...detached.value, {
      panelId, leafId: leaf.id, at: leaf.panels.indexOf(panelId),
      accepts: options.kindOf(panel), fallbackLeafId: nextId("returned"),
    }]
    tree.value = without
    focusedDetached.value = panelId
  }

  function dock(panelId: PanelId) {
    const entry = detached.value.find((one) => one.panelId === panelId)
    if (entry === undefined) return
    tree.value = returnPanel(tree.value, entry)
    detached.value = detached.value.filter((one) => one.panelId !== panelId)
    focusedDetached.value = null
    focusedLeaf.value = leavesOf(tree.value).find((leaf) => leaf.panels.includes(panelId))?.id ?? null
  }

  /**
   * Whether a section takes a panel, and what it would keep without it.
   *
   * The panel is a parameter rather than read from `dragging`, so that the
   * drop applies the very answer the highlight was drawn from: `endDrag`
   * clears the drag before it decides anything.
   */
  function admissionFor(leafId: NodeId, panelId: PanelId | null): DropAdmission {
    const leaf = leavesOf(tree.value).find((one) => one.id === leafId)
    const panel = panelId === null ? undefined : panelOf(panelId)
    if (leaf === undefined || panel === undefined) return { accepts: false, remaining: 0 }
    return {
      // Two opaque strings compared, exactly as placement compares them: a
      // section with no role of its own takes nothing, which is why a split
      // hands its role on. See P1 and P2.
      accepts: leaf.accepts === options.kindOf(panel),
      remaining: leaf.panels.filter((id) => id !== panelId).length,
    }
  }

  function lookOf(panelId: PanelId): PanelLook {
    const panel = panelOf(panelId)
    return panel === undefined ? { title: panelId, icon: "help" } : options.look(panel)
  }

  async function closeOthers(leafId: NodeId) {
    const leaf = leavesOf(tree.value).find((one) => one.id === leafId)
    if (leaf === undefined) return
    // A copy, because closing edits the list this walks.
    for (const panelId of [...leaf.panels]) {
      if (panelId === leaf.activePanel) continue
      // A panel with no cross of its own is not closed by a command that means
      // "the crosses of all the others" - see T3.
      if (lookOf(panelId).closable === false) continue
      // And a panel the cross would have asked about is asked about here too,
      // one at a time so the questions do not arrive in a heap. One kept is
      // kept; the rest still go.
      if (!(await (options.beforeClose?.(panelId) ?? true))) continue
      close(panelId)
    }
  }

  /**
   * The sections that are off the screen.
   *
   * Read off the tree rather than kept beside it, for the reason everything
   * else about where the user is is read off it: a second list could disagree
   * with the layout, and the layout cannot disagree with itself (P7). A
   * section whose role the feature does not name is left out — nothing could
   * draw a way back to it.
   */
  const aside = computed<AsideSection[]>(() =>
    leavesOf(tree.value).flatMap((leaf) => {
      // Nothing is waiting in a section that holds nothing, whatever its flag
      // says: the last tab of a column that was put aside left with it, and a
      // button that brought back an empty column would be a button that makes
      // it disappear again. Opening anything into it brings it back on its own.
      if (leaf.minimized !== true || leaf.panels.length === 0) return []
      const look = options.sectionLook?.(leaf.accepts ?? null) ?? null
      if (look === null) return []
      return [{ id: leaf.id, title: look.title, icon: look.icon, panels: leaf.panels.length }]
    })
  )

  const context: WorkspaceContext = {
    tree,
    panelIds: computed(() => panels.value.map((panel) => panel.id)),
    keyOf,
    detached,
    focusedDetached,
    focusedLeaf,
    dragging,
    lookOf,
    componentOf: (panelId) => {
      const panel = panelOf(panelId)
      if (panel === undefined) throw new Error(`No panel with id ${panelId}`)
      return options.component(panel, keyOf(panelId))
    },
    emptyOf: (accepts) => options.empty?.(accepts) ?? null,
    admissionOf: (leafId) => admissionFor(leafId, dragging.value),
    sectionLookOf: (accepts) => options.sectionLook?.(accepts) ?? null,
    aside,
    collapsedOf: (panelId) => {
      const panel = panelOf(panelId)
      return panel === undefined ? null : (options.collapsed?.(panel) ?? null)
    },
    activate,
    canDetach,
    detach,
    dock,
    onIconClick:
      options.onIconClick === undefined
        ? undefined
        : (panelId) => {
            const panel = panelOf(panelId)
            if (panel !== undefined) options.onIconClick?.(panel)
          },
    close,
    requestClose: async (panelId) => {
      const allowed = await (options.beforeClose?.(panelId) ?? true)
      if (allowed) close(panelId)
      return !panels.value.some((panel) => panel.id === panelId)
    },
    closeOthers,
    focus: (leafId) => {
      focusedLeaf.value = leafId
      focusedDetached.value = null
    },
    firstLeafId: computed(() => leavesOf(tree.value)[0]?.id ?? null),
    hideFirstCollapse: options.hideFirstCollapse === true,
    toggleCollapse: (leafId) => {
      // A workspace of one section has nothing to collapse against, and
      // WorkspaceNode does not offer the handle there either.
      if (tree.value.kind === "leaf") return
      tree.value = setCollapsed(tree.value, leafId, !isCollapsed(tree.value, leafId))
    },
    putAside: (leafId) => {
      // The same guard the handle has: the only section on the screen has
      // nowhere to go, and putting it aside would leave an empty workspace.
      if (tree.value.kind === "leaf") return
      tree.value = setMinimized(tree.value, leafId, true)
    },
    bringBack: (leafId) => {
      tree.value = setMinimized(tree.value, leafId, false)
    },
    resize: (splitId, beforeIndex, afterIndex, delta, minPercent) => {
      tree.value = resizeSplit(tree.value, splitId, beforeIndex, afterIndex, delta, minPercent)
    },
    press: (panelId, x, y) => {
      pressed = { panelId, x, y }
    },
    pointerMoved: (x, y) => {
      if (pressed === null) return
      if (Math.abs(x - pressed.x) + Math.abs(y - pressed.y) < PRESS_THRESHOLD_PX) return
      dragging.value = pressed.panelId
      pressed = null
    },
    endDrag: (targetLeafId, zone, at) => {
      const panelId = dragging.value
      dragging.value = null
      // A press that never became a drag ends here too, or the next movement
      // of the pointer would start one with no button held down.
      pressed = null
      if (panelId === null || targetLeafId === null || zone === null) return
      // The same two rules the highlight was drawn from, applied to the same
      // answer: what is shown and what happens cannot be allowed to differ.
      const allowed = admittedZone(zone, admissionFor(targetLeafId, panelId))
      if (allowed === null) return
      tree.value = movePanel(
        tree.value,
        panelId,
        targetLeafId,
        allowed,
        nextId("leaf"),
        allowed === "center" ? at : undefined
      )
      detached.value = detached.value.filter((entry) => entry.panelId !== panelId)
      focusedDetached.value = null
    },
  }

  function reset() {
    // Assign and let the watcher persist, rather than clearing the key and
    // racing the write that the assignment itself schedules.
    const fresh = options.defaults()
    tree.value = fresh.tree
    panels.value = fresh.panels
    pruneKeys()
    focusedLeaf.value = null
    detached.value = []
    focusedDetached.value = null
    context.endDrag(null, null)
  }

  function snapshot(): string {
    return serializeWorkspace(dockedLayout(tree.value, detached.value), panels.value)
  }

  async function restore(raw: string): Promise<RestoreOutcome> {
    const saved = parseWorkspace(raw, options.panelSchema)
    if (saved === null) return "invalid"
    const incoming = new Map(saved.panels.map((panel) => [panel.id, panel]))
    if (leavesOf(saved.tree).some((leaf) => leaf.panels.some((id) => {
      const panel = incoming.get(id)
      return panel === undefined || (leaf.accepts !== undefined && leaf.accepts !== options.kindOf(panel))
    }))) return "invalid"
    const before = panels.value
    const departing = before.filter((panel) => !incoming.has(panel.id))
    if (departing.some((panel) => lookOf(panel.id).closable === false)) return "invalid"
    // Ask everyone before removing anyone. A nonmodal question lets the user
    // keep working; a changed panel set means these answers no longer apply.
    for (const panel of departing) {
      if (!(await (options.beforeClose?.(panel.id) ?? true))) return "cancelled"
      if (panels.value !== before) return "changed"
    }
    tree.value = saved.tree
    panels.value = saved.panels
    pruneKeys()
    detached.value = []
    focusedLeaf.value = null
    focusedDetached.value = null
    context.endDrag(null, null)
    return "restored"
  }

  return { context, panels, open, replace, snapshot, restore, reset }
}

function isCollapsed(root: LayoutNode, leafId: NodeId): boolean {
  if (root.kind === "leaf") return root.id === leafId && root.collapsed
  return root.children.some((child) => isCollapsed(child, leafId))
}
