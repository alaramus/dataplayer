<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { useCatalogLoader } from "@/features/catalog/api"
import { toTreeRows, rowAt, withChildren } from "@/features/catalog/keyspaceRows"
import type { TreeRow } from "@/features/catalog/keyspaceRows"
import { toListNodes } from "@/features/catalog/nodes"
import type { ListNode } from "@/features/catalog/nodes"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppEmptyState, AppSpinner, AppTree } from "@/shared/ui"
import type { TreeLazyLoad } from "@/shared/ui"

/**
 * A catalog opened where it stands, rather than walked one level at a time.
 *
 * For the sources that say their catalog is a tree (D91): a key space is
 * bounded and its shape is already in the names, so the whole of it is one
 * thing to open and close. Expanding a branch asks the server for that branch,
 * and nothing else about it is different — a leaf is opened in a tab, exactly
 * as it is in the list.
 *
 * Where the tree is rooted is decided outside it: the source's groupings are
 * chosen in the head of the panel, the same control a list uses for schemas,
 * and this is told which one to stand in.
 */
const props = defineProps<{
  connectorId: string
  /** The grouping the tree is rooted in; null is the top of the connection. */
  rootId: string | null
}>()

const emit = defineEmits<{
  /** The node the selection is on, or nothing. Drives the actions menu. */
  select: [node: ListNode | null]
  /** Open this node the way the list opens one: in a tab of its own. */
  open: [node: ListNode]
}>()

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
      toListNodes(await loadChildren(props.connectorId, props.rootId, refresh))
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

watch(
  [() => props.connectorId, () => props.rootId],
  () => void load(),
  { immediate: true }
)

/** What one branch holds, asked for when it is opened. */
async function expand({ node, done, fail }: TreeLazyLoad) {
  const row = node as TreeRow
  try {
    const children = toTreeRows(
      toListNodes(await loadChildren(props.connectorId, row.node.id))
    )
    rows.value = withChildren(rows.value, row.id, children)
    done(children)
  } catch (cause) {
    error.value = messageOf(cause, `Could not open ${row.node.label}`)
    fail()
  }
}

watch(selected, (id) => {
  emit("select", rowAt(rows.value, id)?.node ?? null)
})

/**
 * A click on a leaf opens it, the way a click in the list does.
 *
 * Only a leaf: a branch is a place, and clicking one selects it so that what
 * is made next is made there. Quasar toggles the branch on the same click,
 * which is what a person expects from a tree.
 */
function onClick(row: TreeRow) {
  if (row.node.role === "leaf") emit("open", row.node)
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
             about it. -->
        <div
          class="keyspace__row"
          :data-testid="`keyspace-row-${(node as TreeRow).id}`"
          @click="onClick(node as TreeRow)"
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
