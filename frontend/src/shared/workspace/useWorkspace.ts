import { ref, watch } from "vue"
import type { Component, Ref } from "vue"
import type { ZodType } from "zod"

import { workspaceKey } from "./context"
import type { PanelLook, WorkspaceContext } from "./context"
import { admittedZone } from "./dropZone"
import type { DropAdmission } from "./dropZone"
import { nextId } from "./model"
import type { LayoutNode, NodeId, PanelId } from "./model"
import { parseWorkspace, serializeWorkspace } from "./persist"
import { leafForKind } from "./placement"
import {
  activatePanel,
  addPanel,
  leavesOf,
  movePanel,
  removePanel,
  resizeSplit,
  setCollapsed,
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
   * What renders a panel.
   *
   * Must answer with the same component for the same panel: a tab that is not
   * showing is kept alive, and Vue tells two components apart by identity, so
   * a component built afresh on each call is a different one each time.
   */
  component: (panel: P) => Component
  /** What a pinned section shows while empty, by the role it accepts. */
  empty?: (accepts: string | null) => Component | null
  /**
   * What a collapsed section shows instead of its panel.
   *
   * Same requirement as `component`: the same component for the same panel,
   * or every render replaces it.
   */
  collapsed?: (panel: P) => Component | null
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
  reset: () => void
}

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

  const panelOf = (panelId: PanelId): P | undefined =>
    panels.value.find((panel) => panel.id === panelId)

  // Vue's default flush coalesces every change made in one tick into a single
  // write. flush: "sync" would put a synchronous localStorage write on every
  // frame of a border drag, which is a price the user pays so that a test can
  // skip an await.
  watch(
    [tree, panels],
    () => {
      localStorage.setItem(options.storageKey, serializeWorkspace(tree.value, panels.value))
    },
    { deep: true }
  )

  function open(panel: P, { replace = false }: OpenOptions = {}) {
    if (panelOf(panel.id) !== undefined) {
      tree.value = activatePanel(tree.value, panel.id)
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

  function close(panelId: PanelId) {
    const without = removePanel(tree.value, panelId)
    // The workspace never empties: a screen with no sections at all offers the
    // user nothing to act on and no way back. removePanel answers null for
    // exactly that case, so the rule needs no second guard counting panels -
    // one that could never disagree, and so could never be seen to work.
    if (without === null) return
    tree.value = without
    panels.value = panels.value.filter((panel) => panel.id !== panelId)
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

  function closeOthers(leafId: NodeId) {
    const leaf = leavesOf(tree.value).find((one) => one.id === leafId)
    if (leaf === undefined) return
    for (const panelId of leaf.panels) {
      if (panelId === leaf.activePanel) continue
      // A panel with no cross of its own is not closed by a command that means
      // "the crosses of all the others" - see T3.
      if (lookOf(panelId).closable === false) continue
      close(panelId)
    }
  }

  const context: WorkspaceContext = {
    tree,
    focusedLeaf,
    dragging,
    lookOf,
    componentOf: (panelId) => {
      const panel = panelOf(panelId)
      if (panel === undefined) throw new Error(`No panel with id ${panelId}`)
      return options.component(panel)
    },
    emptyOf: (accepts) => options.empty?.(accepts) ?? null,
    admissionOf: (leafId) => admissionFor(leafId, dragging.value),
    collapsedOf: (panelId) => {
      const panel = panelOf(panelId)
      return panel === undefined ? null : (options.collapsed?.(panel) ?? null)
    },
    activate: (panelId) => {
      tree.value = activatePanel(tree.value, panelId)
    },
    close,
    closeOthers,
    focus: (leafId) => {
      focusedLeaf.value = leafId
    },
    toggleCollapse: (leafId) => {
      // A workspace of one section has nothing to collapse against, and
      // WorkspaceNode does not offer the handle there either.
      if (tree.value.kind === "leaf") return
      tree.value = setCollapsed(tree.value, leafId, !isCollapsed(tree.value, leafId))
    },
    resize: (splitId, beforeIndex, afterIndex, delta, minPercent) => {
      tree.value = resizeSplit(tree.value, splitId, beforeIndex, afterIndex, delta, minPercent)
    },
    startDrag: (panelId) => {
      dragging.value = panelId
    },
    endDrag: (targetLeafId, zone) => {
      const panelId = dragging.value
      dragging.value = null
      if (panelId === null || targetLeafId === null || zone === null) return
      // The same two rules the highlight was drawn from, applied to the same
      // answer: what is shown and what happens cannot be allowed to differ.
      const allowed = admittedZone(zone, admissionFor(targetLeafId, panelId))
      if (allowed === null) return
      tree.value = movePanel(tree.value, panelId, targetLeafId, allowed, nextId("leaf"))
    },
  }

  function reset() {
    // Assign and let the watcher persist, rather than clearing the key and
    // racing the write that the assignment itself schedules.
    const fresh = options.defaults()
    tree.value = fresh.tree
    panels.value = fresh.panels
    focusedLeaf.value = null
  }

  return { context, panels, open, reset }
}

function isCollapsed(root: LayoutNode, leafId: NodeId): boolean {
  if (root.kind === "leaf") return root.id === leafId && root.collapsed
  return root.children.some((child) => isCollapsed(child, leafId))
}
