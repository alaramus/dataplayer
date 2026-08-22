import { ref, watch } from "vue"
import type { Component, Ref } from "vue"
import type { ZodType } from "zod"

import { workspaceKey } from "./context"
import type { PanelLook, WorkspaceContext } from "./context"
import { nextId } from "./model"
import type { LayoutNode, NodeId, PanelId } from "./model"
import { parseWorkspace, serializeWorkspace } from "./persist"
import { leafForKind } from "./placement"
import { activatePanel, addPanel, movePanel, removePanel, resizeSplit, setCollapsed } from "./tree"

export { workspaceKey }
export type { PanelLook, WorkspaceContext }

export interface WorkspaceOptions<P extends { id: string }> {
  storageKey: string
  panelSchema: ZodType<P>
  defaults: () => { tree: LayoutNode; panels: P[] }
  kindOf: (panel: P) => string
  look: (panel: P) => PanelLook
  component: (panel: P) => Component
}

export interface WorkspaceApi<P extends { id: string }> {
  context: WorkspaceContext
  panels: Ref<P[]>
  open: (panel: P) => void
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

  watch(
    [tree, panels],
    () => {
      localStorage.setItem(options.storageKey, serializeWorkspace(tree.value, panels.value))
    },
    { deep: true, flush: "sync" }
  )

  function open(panel: P) {
    if (panelOf(panel.id) !== undefined) {
      tree.value = activatePanel(tree.value, panel.id)
      return
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
    // The workspace never empties: a screen with no sections at all offers the
    // user nothing to act on, and no way back.
    if (panels.value.length <= 1) return
    const without = removePanel(tree.value, panelId)
    if (without === null) return
    tree.value = without
    panels.value = panels.value.filter((panel) => panel.id !== panelId)
  }

  const context: WorkspaceContext = {
    tree,
    focusedLeaf,
    dragging,
    lookOf: (panelId) => {
      const panel = panelOf(panelId)
      return panel === undefined ? { title: panelId, icon: "help" } : options.look(panel)
    },
    componentOf: (panelId) => {
      const panel = panelOf(panelId)
      if (panel === undefined) throw new Error(`No panel with id ${panelId}`)
      return options.component(panel)
    },
    activate: (panelId) => {
      tree.value = activatePanel(tree.value, panelId)
    },
    close,
    focus: (leafId) => {
      focusedLeaf.value = leafId
    },
    toggleCollapse: (leafId) => {
      // A workspace of one section has nothing to collapse against, and
      // WorkspaceNode does not offer the handle there either.
      if (tree.value.kind === "leaf") return
      tree.value = setCollapsed(tree.value, leafId, !collapsedOf(tree.value, leafId))
    },
    resize: (splitId, index, delta, minPercent) => {
      tree.value = resizeSplit(tree.value, splitId, index, delta, minPercent)
    },
    startDrag: (panelId) => {
      dragging.value = panelId
    },
    endDrag: (targetLeafId, zone) => {
      const panelId = dragging.value
      dragging.value = null
      if (panelId === null || targetLeafId === null || zone === null) return
      tree.value = movePanel(tree.value, panelId, targetLeafId, zone, nextId("leaf"))
    },
  }

  function reset() {
    const fresh = options.defaults()
    tree.value = fresh.tree
    panels.value = fresh.panels
    focusedLeaf.value = null
    // The [tree, panels] watcher above is flush: "sync", so the assignments
    // just above already wrote the defaults back to storage. Clearing the key
    // has to happen after them, or the sync write would undo it immediately.
    localStorage.removeItem(options.storageKey)
  }

  return { context, panels, open, reset }
}

function collapsedOf(root: LayoutNode, leafId: NodeId): boolean {
  if (root.kind === "leaf") return root.id === leafId && root.collapsed
  return root.children.some((child) => collapsedOf(child, leafId))
}
