<script setup lang="ts">
import { computed, nextTick, ref, useTemplateRef, watch } from "vue"

import { useCatalogLoader } from "@/features/catalog/api"
import type { NodeMatch } from "@/client"
import { filterTree, foundTree, toTreeRows, rowAt, withChildren } from "@/features/catalog/keyspaceRows"
import type { TreeRow } from "@/features/catalog/keyspaceRows"
import { toListNodes } from "@/features/catalog/nodes"
import type { ListNode } from "@/features/catalog/nodes"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppBanner, AppEmptyState, AppSpinner, AppTree } from "@/shared/ui"
import type { TreeLazyLoad } from "@/shared/ui"

/**
 * A catalog opened where it stands rather than walked a level at a time, for
 * sources that say their catalog is a tree (D91): a key space is bounded and
 * its shape is already in the names. Expanding a branch asks the server for
 * that branch, and a leaf opens in a tab exactly as it does in the list.
 */
const props = defineProps<{
  connectorId: string
  /** The grouping the tree is rooted in; null is the top of the connection. */
  rootId: string | null
  /** Narrows what has been read, as the list's filter does. */
  filter?: string
  /** A search's matches, drawn in place of the tree while they are here. */
  found?: readonly NodeMatch[] | null
}>()

const emit = defineEmits<{
  /** The node the selection is on, or nothing. Drives the actions menu. */
  select: [node: ListNode | null]
  /** Open this node the way the list opens one: in a tab of its own. */
  open: [node: ListNode]
}>()

const loadChildren = useCatalogLoader()

const tree = useTemplateRef<{
  setExpanded: (key: string, open: boolean) => void
  isExpanded: (key: string) => boolean
}>("tree")
const root = useTemplateRef<HTMLElement>("root")

const rows = ref<TreeRow[]>([])
/** The search's tree, kept apart so opening a found folder reads into it. */
const foundRows = ref<TreeRow[] | null>(null)
const expanded = ref<string[]>([])
/** What was open before a search opened its own way down. */
let openBefore: string[] = []
const selected = ref<string | null>(null)
const loading = ref(false)
const error = ref("")

async function load(refresh = false) {
  loading.value = true
  error.value = ""
  try {
    rows.value = toTreeRows(
      toListNodes((await loadChildren(props.connectorId, props.rootId, refresh)).nodes)
    )
    // What was open was open about the last reading; a branch that is gone
    // would keep an arrow pointing at nothing.
    expanded.value = []
    selected.value = null
  } catch (cause) {
    error.value = messageOf(cause, t("catalog.level.read_failed"))
    rows.value = []
  } finally {
    loading.value = false
  }
}

// The reading in progress, so `reveal` opens branches of the tree that is
// about to be drawn rather than of the one it replaces.
let reading: Promise<void> = Promise.resolve()

watch(
  [() => props.connectorId, () => props.rootId],
  () => { reading = load() },
  { immediate: true }
)

async function childrenOf(id: string): Promise<TreeRow[]> {
  return toTreeRows(toListNodes((await loadChildren(props.connectorId, id)).nodes))
}

/** What one branch holds, asked for when it is opened. */
async function expand({ node, done, fail }: TreeLazyLoad) {
  const row = node as TreeRow
  try {
    const children = await childrenOf(row.node.id)
    if (foundRows.value === null) rows.value = withChildren(rows.value, row.id, children)
    else foundRows.value = withChildren(foundRows.value, row.id, children)
    done(children)
  } catch (cause) {
    error.value = messageOf(cause, t("catalog.keyspace.open_failed", { name: row.node.label }))
    fail()
  }
}

/**
 * Open the branches on the way to a node, top first, and select it.
 *
 * The branches are the ones the source named in its path (D21). A branch's
 * children are read here and put in place before it is marked open: marked
 * open with nothing under it, a lazy branch asks for nothing and stays shut.
 */
async function reveal(branches: string[], nodeId: string) {
  await reading
  for (const id of branches) {
    const row = rowAt(rows.value, id)
    if (row === null) return
    if (row.lazy === true) rows.value = withChildren(rows.value, id, await childrenOf(id))
    if (!expanded.value.includes(id)) expanded.value = [...expanded.value, id]
  }
  if (rowAt(rows.value, nodeId) === null) return
  selected.value = nodeId
  await nextTick()
  root.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" })
}

const filtered = computed(() => filterTree(rows.value, props.filter ?? ""))
const shown = computed(() => foundRows.value ?? filtered.value.rows)

// The branches a match stayed for are opened as the words change, and stay
// open after: each of them has been read, so none is a lazy branch marked open
// with nothing under it.
watch(() => filtered.value.open, (open) => {
  const missing = open.filter((id) => !expanded.value.includes(id))
  if (missing.length > 0) expanded.value = [...expanded.value, ...missing]
})

// A search's places are its own, so leaving it restores what was open: the
// tree under it never read most of them.
watch(() => props.found ?? null, (matches) => {
  if (matches === null) {
    if (foundRows.value === null) return
    foundRows.value = null
    expanded.value = openBefore
    return
  }
  if (foundRows.value === null) openBefore = expanded.value
  const built = foundTree(matches, props.rootId, rows.value)
  foundRows.value = built.rows
  expanded.value = built.open
}, { immediate: true })

watch(selected, (id) => {
  emit("select", rowAt(shown.value, id)?.node ?? null)
})

/**
 * A click is on the whole row, wherever in it the pointer landed. With a
 * selection bound the tree selects on a click and does nothing else, which is
 * why opening a branch is here: a name is a bigger target than the arrow
 * beside it, and reaching for that arrow is what made this tree feel stiff.
 *
 * Nothing here touches the selection — a second answer arriving a moment
 * before the tree's own turned every click into a select and an unselect.
 */
function onClick(row: TreeRow) {
  if (row.node.role === "leaf") {
    emit("open", row.node)
    return
  }
  // Through the tree's own method rather than by pushing a key into
  // `expanded`: a branch asks for its children as it opens, and setting the
  // array from outside marks it open and asks for nothing — so it stayed shut
  // with an arrow pointing the wrong way.
  tree.value?.setExpanded(row.id, !tree.value.isExpanded(row.id))
}

const empty = computed(() => !loading.value && shown.value.length === 0)
const emptyText = computed(() =>
  foundRows.value !== null || filtered.value.rows !== rows.value
    ? t("catalog.keyspace.nothing_matches")
    : t("catalog.keyspace.nothing_yet")
)

function reload(): Promise<void> {
  reading = load(true)
  return reading
}

defineExpose({ reload, reveal })
</script>

<template>
  <div
    ref="root"
    class="keyspace"
  >
    <AppBanner
      v-if="error"
      tone="error"
      data-testid="keyspace-error"
    >
      {{ error }}
    </AppBanner>

    <AppSpinner v-if="loading" />
    <AppEmptyState
      v-else-if="empty"
      icon="vpn_key"
      :text="emptyText"
    />
    <AppTree
      v-else
      ref="tree"
      v-model:expanded="expanded"
      v-model:selected="selected"
      keep-selection
      class="keyspace__tree"
      :nodes="shown"
      node-key="id"
      data-testid="keyspace-tree"
      @lazy-load="expand"
    >
      <template #default-header="{ node }">
        <!-- One row: what it is, what it is called, and what the source said
             about it. -->
        <div
          class="keyspace__row"
          :data-testid="`keyspace-row-${(node as TreeRow).id}`"
          :aria-selected="selected === (node as TreeRow).id"
          @click="onClick(node as TreeRow)"
        >
          <q-icon
            :name="(node as TreeRow).icon"
            size="var(--dp-icon-sm)"
          />
          <span class="keyspace__label">{{ (node as TreeRow).label }}</span>
          <span
            v-if="(node as TreeRow).caption"
            class="keyspace__caption"
          >{{ (node as TreeRow).caption }}</span>
        </div>
      </template>
    </AppTree>
  </div>
</template>

<style scoped>
.keyspace {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--dp-space-1) var(--dp-space-half);
}
.keyspace__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  min-width: 0;
  flex: 1;
}
.keyspace__label {
  font-size: var(--dp-font-size);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.keyspace__caption {
  font-size: var(--dp-font-size-xs);
  color: var(--dp-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
</style>
