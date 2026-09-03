<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { useCatalogLoader } from "@/features/catalog/api"
import { toTreeRows, toValueRows, rowAt, withChildren } from "@/features/catalog/keyspaceRows"
import type { TreeRow } from "@/features/catalog/keyspaceRows"
import { toListNodes } from "@/features/catalog/nodes"
import type { ListNode } from "@/features/catalog/nodes"
import { fetchRowsPage } from "@/features/grid/api"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppEmptyState, AppSpinner, AppTree } from "@/shared/ui"
import type { TreeLazyLoad } from "@/shared/ui"

/**
 * A catalog opened where it stands, rather than walked one level at a time.
 *
 * For the sources that say their catalog is a tree (D91): a key space is
 * bounded, its shape is already in the names, and what a key holds is a few
 * fields worth seeing beside the key. Expanding a branch asks the server for
 * that branch; expanding a leaf asks for a page of what it holds, which is
 * what gives this the feel of a JSON viewer rather than of a file manager.
 *
 * Opening a leaf properly — with paging, the full value and everything the
 * grid offers — is still a tab, and a double click is how one is asked for.
 */
const props = defineProps<{
  connectorId: string
  /** How many of a node's own rows are shown inside the tree. */
  peek?: number
}>()

const emit = defineEmits<{
  /** The node the selection is on, or nothing. Drives the actions menu. */
  select: [node: ListNode | null]
  /** Open this node the way the list opens one: in a tab of its own. */
  open: [node: ListNode]
}>()

/** How much of a node is shown inside the tree before it says "open it". */
const PEEK = 50

const loadChildren = useCatalogLoader()

const rows = ref<TreeRow[]>([])
const expanded = ref<string[]>([])
const selected = ref<string | null>(null)
const loading = ref(false)
const error = ref("")

async function load(refresh = false) {
  loading.value = true
  error.value = ""
  try {
    rows.value = toTreeRows(
      toListNodes(await loadChildren(props.connectorId, null, refresh))
    )
    // What was open was open about the last reading; a branch that is gone
    // would keep an arrow pointing at nothing.
    expanded.value = []
    selected.value = null
  } catch (cause) {
    error.value = messageOf(cause, "Could not read the catalog")
    rows.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.connectorId, () => void load(), { immediate: true })

/**
 * What one branch holds, asked for when it is opened.
 *
 * Two answers from one handler, because the tree makes one request: a node
 * with children answers with them, and a node without answers with a page of
 * what it holds. Which of the two it is was already decided by the source,
 * and is read off the node rather than off the type of the connection.
 */
async function expand({ node, done, fail }: TreeLazyLoad) {
  const row = node as TreeRow
  const listed = row.node
  if (listed === undefined) {
    done([])
    return
  }
  try {
    const children =
      listed.role === "leaf" ? await peekInto(listed) : await branchOf(listed)
    rows.value = withChildren(rows.value, row.id, children)
    done(children)
  } catch (cause) {
    error.value = messageOf(cause, `Could not open ${listed.label}`)
    fail()
  }
}

async function branchOf(node: ListNode): Promise<TreeRow[]> {
  return toTreeRows(toListNodes(await loadChildren(props.connectorId, node.id)))
}

async function peekInto(node: ListNode): Promise<TreeRow[]> {
  const page = await fetchRowsPage(
    props.connectorId,
    { node_id: node.id, limit: props.peek ?? PEEK },
    new AbortController().signal
  )
  return toValueRows(node.id, page)
}

watch(selected, (id) => {
  emit("select", rowAt(rows.value, id)?.node ?? null)
})

function onActivate(row: TreeRow) {
  if (row.node !== undefined && row.node.readable) emit("open", row.node)
}

const empty = computed(() => !loading.value && rows.value.length === 0)

defineExpose({ reload: () => load(true) })
</script>

<template>
  <div class="keyspace">
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
      text="Nothing here yet."
    />
    <AppTree
      v-else
      v-model:expanded="expanded"
      v-model:selected="selected"
      class="keyspace__tree"
      :nodes="rows"
      node-key="id"
      data-testid="keyspace-tree"
      @lazy-load="expand"
    >
      <template #default-header="{ node }">
        <!-- One row: what it is, what it is called, and what the source said
             about it. A double click opens it the way the list does. -->
        <div
          class="keyspace__row"
          :data-testid="`keyspace-row-${(node as TreeRow).id}`"
          @dblclick="onActivate(node as TreeRow)"
        >
          <q-icon
            :name="(node as TreeRow).icon"
            size="16px"
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
  padding: 4px 2px;
}
.keyspace__row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}
.keyspace__label {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.keyspace__caption {
  font-size: 11px;
  color: var(--dp-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
</style>
