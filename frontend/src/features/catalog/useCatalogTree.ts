import { useQueryClient } from "@tanstack/vue-query"
import { computed, ref } from "vue"
import type { ComputedRef, Ref } from "vue"

import { catalogKey, useCatalogLoader } from "@/features/catalog/api"
import { toTreeNodes } from "@/features/catalog/treeNodes"
import type { TreeNode } from "@/features/catalog/treeNodes"
import { messageOf } from "@/shared/api/errors"

export interface CatalogTree {
  roots: Ref<TreeNode[]>
  expanded: Ref<string[]>
  selectedId: Ref<string | null>
  selected: ComputedRef<TreeNode | null>
  loading: Ref<boolean>
  error: Ref<string>
  load: () => Promise<void>
  reload: (nodeId: string | null) => Promise<void>
  onLazyLoad: (payload: {
    node: TreeNode
    done: (children: TreeNode[]) => void
    fail: () => void
  }) => Promise<void>
}

/**
 * Walking a catalog one level at a time.
 *
 * Lives apart from any component: it was never logic of a dialog, and the
 * workspace panel needs the same behaviour without one.
 */
export function useCatalogTree(connectorId: Ref<string>): CatalogTree {
  const loadChildren = useCatalogLoader()
  const queryClient = useQueryClient()

  const roots = ref<TreeNode[]>([])
  const expanded = ref<string[]>([])
  const loading = ref(false)
  const error = ref("")

  // Every node ever loaded, so a selection resolves to its kind without
  // walking the tree.
  const nodesById = ref(new Map<string, TreeNode>())
  const selectedId = ref<string | null>(null)

  const selected = computed(() =>
    selectedId.value === null ? null : (nodesById.value.get(selectedId.value) ?? null)
  )

  function remember(nodes: TreeNode[]) {
    for (const node of nodes) nodesById.value.set(node.id, node)
  }

  async function load() {
    roots.value = []
    expanded.value = []
    nodesById.value = new Map()
    selectedId.value = null
    error.value = ""
    loading.value = true
    try {
      roots.value = toTreeNodes(await loadChildren(connectorId.value, null))
      remember(roots.value)
    } catch (cause) {
      error.value = messageOf(cause, "Could not read the catalog")
    } finally {
      loading.value = false
    }
  }

  /**
   * Re-read one branch after something changed it.
   *
   * The branch is invalidated here rather than trusted to have been
   * invalidated by whoever changed it: the loader answers from the cache while
   * the page is fresh, so a reload that did not say so would hand back exactly
   * what it was asked to replace. And invalidating is not enough on its own —
   * the tree keeps the children on the node object, so they have to be put
   * back as well.
   */
  async function reload(nodeId: string | null) {
    await queryClient.invalidateQueries({ queryKey: catalogKey(connectorId.value, nodeId) })

    const node = nodeId === null ? null : (nodesById.value.get(nodeId) ?? null)
    const previous = node ? (node.children ?? []) : roots.value
    const wasHere = previous.some((child) => child.id === selectedId.value)

    const children = toTreeNodes(await loadChildren(connectorId.value, nodeId))
    remember(children)

    if (node) {
      node.children = children
      node.lazy = false
      if (!expanded.value.includes(node.id)) expanded.value = [...expanded.value, node.id]
    } else {
      roots.value = children
    }

    // A selection removed by the action must not linger: it would name a node
    // that is no longer there.
    if (wasHere && !children.some((child) => child.id === selectedId.value)) {
      selectedId.value = null
    }
  }

  async function onLazyLoad({
    node,
    done,
    fail,
  }: {
    node: TreeNode
    done: (children: TreeNode[]) => void
    fail: () => void
  }) {
    try {
      const children = toTreeNodes(await loadChildren(connectorId.value, node.id))
      remember(children)
      done(children)
    } catch (cause) {
      error.value = messageOf(cause, "Could not read the catalog")
      fail()
    }
  }

  return { roots, expanded, selectedId, selected, loading, error, load, reload, onLazyLoad }
}
