import { useQueryClient } from "@tanstack/vue-query"
import { computed, ref, watch } from "vue"
import type { ComputedRef, Ref } from "vue"

import type { NodeReplacement } from "@/client"
import { catalogKey, useCatalogLoader, useNodeSearcher } from "@/features/catalog/api"
import type { Crumb, Location } from "@/features/catalog/location"
import { groupsOf, toListNodes } from "@/features/catalog/nodes"
import type { ListNode } from "@/features/catalog/nodes"
import { foundNodes } from "@/features/catalog/search"
import type { FoundNodes } from "@/features/catalog/search"
import { messageOf } from "@/shared/api/errors"

export type { Crumb } from "@/features/catalog/location"

export interface CatalogLevel {
  path: Ref<Crumb[]>
  currentId: ComputedRef<string | null>
  /** The groupings this level offers, shown as a filter above the list. */
  groups: Ref<ListNode[]>
  selectedGroups: Ref<string[]>
  setGroups: (ids: string[]) => Promise<void>
  filter: Ref<string>
  items: ComputedRef<ListNode[]>
  /**
   * The search that is being shown instead of the level, or nothing (D76).
   *
   * A state of the level rather than a screen of its own: the same list, the
   * same ticks and the same menu act on what a search found, and anything that
   * changes the level — walking, reloading, an action — ends it.
   */
  found: Ref<FoundNodes | null>
  searching: Ref<boolean>
  /** Look for the filter text below this level. Does nothing while it is empty. */
  search: () => Promise<void>
  /** Back to the folder, keeping the words that were searched for. */
  clearSearch: () => void
  checked: Ref<string[]>
  checkedNodes: ComputedRef<ListNode[]>
  allChecked: ComputedRef<boolean>
  loading: Ref<boolean>
  error: Ref<string>
  load: () => Promise<void>
  enter: (node: ListNode) => Promise<void>
  up: () => Promise<void>
  goTo: (index: number) => Promise<void>
  showLocation: (location: Location) => Promise<void>
  reload: (nodeId: string | null) => Promise<void>
  reloadMany: (nodeIds: (string | null)[]) => Promise<void>
  /** Apply one exact source-issued identity change before the reload lands. */
  replaceNode: (replacement: NodeReplacement) => void
  toggleAll: (on: boolean) => void
}

/**
 * Walking a catalog one level at a time, as a list rather than a tree.
 *
 * Lives apart from any component: it was never logic of a screen, and what it
 * holds — where we are, what is ticked, which groupings are on — outlives any
 * one of them. What varies between sources is read off the role of a node and
 * nothing else; see `nodes.ts`.
 */
export function useCatalogLevel(connectorId: Ref<string>, rootLabel: Ref<string>): CatalogLevel {
  const loadChildren = useCatalogLoader()
  const searchNodes = useNodeSearcher()
  const queryClient = useQueryClient()

  const path = ref<Crumb[]>([{ id: null, label: rootLabel.value }])
  const groups = ref<ListNode[]>([])
  const selectedGroups = ref<string[]>([])
  const rows = ref<ListNode[]>([])
  // The children of the level itself, kept apart from the children of the
  // groupings so that ticking a grouping rebuilds the list without re-reading
  // the level.
  const plain = ref<ListNode[]>([])
  const checked = ref<string[]>([])
  const filter = ref("")
  const loading = ref(false)
  const error = ref("")
  const found = ref<FoundNodes | null>(null)
  const searching = ref(false)

  const currentId = computed(() => path.value[path.value.length - 1]?.id ?? null)

  /**
   * The rows the list is drawing from: a level, or what a search found.
   *
   * One place, so the filter, the ticks and "select all" mean the same thing
   * in both states rather than each having to know which one it is in.
   */
  const shown = computed(() => found.value?.rows ?? rows.value)

  const items = computed(() => {
    const needle = filter.value.trim().toLowerCase()
    if (needle === "") return shown.value
    return shown.value.filter((node) => node.label.toLowerCase().includes(needle))
  })

  const checkedNodes = computed(() =>
    shown.value.filter((node) => checked.value.includes(node.id))
  )

  const allChecked = computed(
    () => items.value.length > 0 && items.value.every((node) => checked.value.includes(node.id))
  )

  // The root crumb carries the name of the connection, which is not known
  // until the list of connections has been read.
  watch(rootLabel, (label) => {
    const root = path.value[0]
    if (root !== undefined) root.label = label
  })

  async function childrenOf(
    nodeId: string | null,
    group?: string,
    refresh = false
  ): Promise<ListNode[]> {
    return toListNodes(await loadChildren(connectorId.value, nodeId, refresh), group)
  }

  async function forget(nodeId: string | null) {
    await queryClient.invalidateQueries({ queryKey: catalogKey(connectorId.value, nodeId) })
  }

  /**
   * What the list shows: the plain children of the level, plus the children of
   * every grouping that is ticked.
   *
   * The two are concatenated rather than one replacing the other, so a source
   * whose level holds both keeps both. Nothing does today.
   */
  async function fillRows(refresh = false) {
    const grouped: ListNode[] = []
    for (const group of groups.value) {
      if (!selectedGroups.value.includes(group.id)) continue
      grouped.push(...(await childrenOf(group.id, group.label, refresh)))
    }
    rows.value = [...plain.value, ...grouped]
  }

  /** Which groupings are on before the user has chosen: the first real one. */
  function defaultGroups(offered: ListNode[]): string[] {
    const first = offered.find((group) => !group.system) ?? offered[0]
    return first === undefined ? [] : [first.id]
  }

  /** Keep an explicit grouping choice only while those groupings still exist. */
  function availableGroups(requested: string[] | undefined, offered: ListNode[]): string[] {
    if (requested === undefined) return defaultGroups(offered)
    const offeredIds = new Set(offered.map((group) => group.id))
    const remaining = requested.filter((id) => offeredIds.has(id))
    return remaining.length > 0 || requested.length === 0
      ? remaining
      : defaultGroups(offered)
  }

  async function show(nodeId: string | null, groupIds?: string[], refresh = false) {
    checked.value = []
    filter.value = ""
    // Any change of level ends a search: what is on screen is a level again,
    // and results from the folder that was left would say nothing about it.
    found.value = null
    error.value = ""
    loading.value = true
    try {
      const children = await childrenOf(nodeId, undefined, refresh)
      groups.value = groupsOf(children)
      selectedGroups.value = availableGroups(groupIds, groups.value)
      plain.value = children.filter((node) => node.role !== "group")
      await fillRows(refresh)
    } catch (cause) {
      error.value = messageOf(cause, "Could not read the catalog")
      groups.value = []
      selectedGroups.value = []
      plain.value = []
      rows.value = []
    } finally {
      loading.value = false
    }
  }

  /**
   * Tick a different set of groupings: the list is read again, the level is
   * not. A method rather than a watcher on `selectedGroups`, so that assigning
   * the default set inside `show` does not read everything twice — and so that
   * a caller can wait for the list it asked for.
   */
  async function setGroups(ids: string[]) {
    selectedGroups.value = ids
    checked.value = []
    loading.value = true
    try {
      await fillRows()
      error.value = ""
    } catch (cause) {
      error.value = messageOf(cause, "Could not read the catalog")
      rows.value = []
    } finally {
      loading.value = false
    }
  }

  async function load() {
    path.value = [{ id: null, label: rootLabel.value }]
    await show(null)
  }

  async function enter(node: ListNode) {
    if (node.role !== "container") return
    path.value = [...path.value, { id: node.id, label: node.label }]
    await show(node.id)
  }

  async function up() {
    if (path.value.length < 2) return
    path.value = path.value.slice(0, -1)
    await show(currentId.value)
  }

  async function goTo(index: number) {
    if (index < 0 || index >= path.value.length - 1) return
    path.value = path.value.slice(0, index + 1)
    await show(currentId.value)
  }

  /**
   * Stand where a node lives, as the source said it lives there.
   *
   * The level is only re-read when it is not already the right one: `show`
   * clears the ticks and the filter, and pointing at a row that is on screen
   * already is no reason to take a user's ticks away. The comparison is one
   * of ids for equality — nothing here reads what an id is made of.
   */
  async function showLocation(location: Location) {
    const sameLevel = currentId.value === location.parentId
    const sameGroups = location.groups.every((id) =>
      selectedGroups.value.includes(id)
    )
    if (sameLevel && sameGroups) return

    path.value = [{ id: null, label: rootLabel.value }, ...location.crumbs]
    await show(location.parentId, location.groups)
  }

  /**
   * Re-read the level after something changed it.
   *
   * The branch is forgotten here rather than trusted to have been forgotten by
   * whoever changed it: the loader answers from the cache while the page is
   * fresh, so a reload that did not say so would hand back exactly what it was
   * asked to replace.
   */
  async function reloadMany(nodeIds: (string | null)[]) {
    const groupsToKeep = [...selectedGroups.value]
    const branches = new Set<string | null>([
      ...nodeIds,
      currentId.value,
      ...selectedGroups.value,
    ])
    for (const nodeId of branches) await forget(nodeId)
    await show(currentId.value, groupsToKeep, true)
  }

  async function reload(nodeId: string | null) {
    await reloadMany([nodeId])
  }

  function replaceNode(replacement: NodeReplacement) {
    const replaceId = (id: string) =>
      id === replacement.old_node_id ? replacement.new_node_id : id
    const replaceListNode = (node: ListNode): ListNode =>
      node.id === replacement.old_node_id
        ? { ...node, id: replacement.new_node_id, label: replacement.title }
        : node

    path.value = path.value.map((crumb) =>
      crumb.id === replacement.old_node_id
        ? { id: replacement.new_node_id, label: replacement.title }
        : crumb
    )
    groups.value = groups.value.map(replaceListNode)
    selectedGroups.value = selectedGroups.value.map(replaceId)
    plain.value = plain.value.map(replaceListNode)
    rows.value = rows.value.map(replaceListNode)
    checked.value = checked.value.map(replaceId)
  }

  function toggleAll(on: boolean) {
    checked.value = on ? items.value.map((node) => node.id) : []
  }

  /**
   * Look for the filter text everywhere below this level.
   *
   * The words are the ones already typed: the filter narrows what is here, and
   * this asks the source for what is not. The ticks go, because they were
   * ticks on a different list.
   */
  async function search() {
    const query = filter.value.trim()
    if (query === "") return
    searching.value = true
    try {
      found.value = foundNodes(query, await searchNodes(connectorId.value, currentId.value, query))
      checked.value = []
      error.value = ""
    } catch (cause) {
      error.value = messageOf(cause, "Could not search this connection")
    } finally {
      searching.value = false
    }
  }

  /** Back to the level, with the words kept: they are a filter again. */
  function clearSearch() {
    found.value = null
    checked.value = []
  }

  return {
    path,
    currentId,
    groups,
    selectedGroups,
    setGroups,
    filter,
    items,
    found,
    searching,
    search,
    clearSearch,
    checked,
    checkedNodes,
    allChecked,
    loading,
    error,
    load,
    enter,
    up,
    goTo,
    showLocation,
    reload,
    reloadMany,
    replaceNode,
    toggleAll,
  }
}
