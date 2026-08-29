import { useQueryClient } from "@tanstack/vue-query"
import { computed, ref, watch } from "vue"
import type { ComputedRef, Ref } from "vue"

import { catalogKey, useCatalogLoader } from "@/features/catalog/api"
import type { Crumb, Location } from "@/features/catalog/location"
import { groupsOf, toListNodes } from "@/features/catalog/nodes"
import type { ListNode } from "@/features/catalog/nodes"
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

  const currentId = computed(() => path.value[path.value.length - 1]?.id ?? null)

  const items = computed(() => {
    const needle = filter.value.trim().toLowerCase()
    if (needle === "") return rows.value
    return rows.value.filter((node) => node.label.toLowerCase().includes(needle))
  })

  const checkedNodes = computed(() =>
    rows.value.filter((node) => checked.value.includes(node.id))
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

  async function show(nodeId: string | null, groupIds?: string[], refresh = false) {
    checked.value = []
    filter.value = ""
    error.value = ""
    loading.value = true
    try {
      const children = await childrenOf(nodeId, undefined, refresh)
      groups.value = groupsOf(children)
      selectedGroups.value = groupIds ?? defaultGroups(groups.value)
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
  async function reload(nodeId: string | null) {
    await forget(nodeId)
    await forget(currentId.value)
    for (const group of selectedGroups.value) await forget(group)
    await show(currentId.value, undefined, true)
  }

  function toggleAll(on: boolean) {
    checked.value = on ? items.value.map((node) => node.id) : []
  }

  return {
    path,
    currentId,
    groups,
    selectedGroups,
    setGroups,
    filter,
    items,
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
    toggleAll,
  }
}
