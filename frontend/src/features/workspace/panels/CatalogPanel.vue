<script setup lang="ts">
import { computed, onMounted } from "vue"

import ActionBar from "@/features/catalog/ActionBar.vue"
import { useCatalogTree } from "@/features/catalog/useCatalogTree"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppBanner, AppEmptyState, AppSpinner, AppTree } from "@/shared/ui"

const props = defineProps<{ connectorId: string }>()

const workspace = useWorkspaceActions()
const connectorId = computed(() => props.connectorId)
const tree = useCatalogTree(connectorId)

onMounted(() => {
  void tree.load()
})

const targetLabel = computed(() => tree.selected.value?.label ?? "Whole connection")

/**
 * A file nothing can read as rows.
 *
 * Said here rather than left silent: selecting such a file opens no tab, and
 * without a word the click looks like it did nothing at all.
 */
const selectedOpaque = computed(() => {
  const node = tree.selected.value
  return node !== null && node.kind === "file" && !node.readable ? node : null
})

/** Selecting a readable node opens it in the section that holds rows. */
function onSelected(nodeId: string | null) {
  tree.selectedId.value = nodeId
  const node = tree.selected.value
  if (node !== null && node.readable) {
    workspace.openRows(props.connectorId, node.id, node.label)
  }
}
</script>

<template>
  <div class="catalog-panel">
    <AppBanner
      v-if="tree.error.value"
      tone="error"
      data-testid="catalog-error"
    >
      {{ tree.error.value }}
    </AppBanner>

    <ActionBar
      v-if="!tree.loading.value"
      :connector-id="connectorId"
      :node-id="tree.selectedId.value"
      :node-label="targetLabel"
      @done="tree.reload"
    />

    <AppSpinner v-if="tree.loading.value" />

    <!-- The tree has no caption prop, so the header is rendered here: the
         default one would show the label alone and silently drop the data type
         and the row estimate. -->
    <AppTree
      v-else-if="tree.roots.value.length"
      v-model:expanded="tree.expanded.value"
      :nodes="tree.roots.value"
      :selected="tree.selectedId.value"
      node-key="id"
      data-testid="catalog-tree"
      @update:selected="onSelected"
      @lazy-load="tree.onLazyLoad"
    >
      <template #default-header="{ node }">
        <q-icon
          :name="node.icon"
          size="20px"
          class="q-mr-sm"
        />
        <span>{{ node.label }}</span>
        <span
          v-if="node.caption"
          class="text-caption text-grey q-ml-sm"
        >
          {{ node.caption }}
        </span>
      </template>
    </AppTree>

    <AppEmptyState
      v-else-if="!tree.error.value"
      text="Nothing to show"
    />

    <div
      v-if="selectedOpaque"
      data-testid="opaque-file"
    >
      <AppEmptyState :text="`${selectedOpaque.label} cannot be read as rows.`" />
    </div>
  </div>
</template>

<style scoped>
.catalog-panel {
  padding: 8px;
}
</style>
