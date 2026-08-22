<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ConnectorPublic } from "@/client"
import ActionBar from "@/features/catalog/ActionBar.vue"
import RowGrid from "@/features/catalog/RowGrid.vue"
import { useCatalogLoader } from "@/features/catalog/api"
import { toTreeNodes } from "@/features/catalog/treeNodes"
import type { TreeNode } from "@/features/catalog/treeNodes"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppDialog,
  AppEmptyState,
  AppSection,
  AppSpinner,
} from "@/shared/ui"

const props = defineProps<{
  modelValue: boolean
  connector: ConnectorPublic | null
}>()

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()

const loadChildren = useCatalogLoader()

const roots = ref<TreeNode[]>([])
const expanded = ref<string[]>([])
const loading = ref(false)
const error = ref("")

// Every node ever loaded, so a selection can be resolved to its kind without
// walking the tree.
const nodesById = ref(new Map<string, TreeNode>())
const selectedId = ref<string | null>(null)

const selected = computed(() =>
  selectedId.value ? (nodesById.value.get(selectedId.value) ?? null) : null
)

// What carries rows is decided by the mapper, not here: a table, a view and a
// readable file all show a grid; a schema, a column and a directory show
// nothing.
const selectedRelation = computed(() => (selected.value?.readable ? selected.value : null))

// A picture or an archive deserves a word rather than a blank panel that
// looks like nothing was selected.
const selectedOpaque = computed(() =>
  selected.value && selected.value.kind === "file" && !selected.value.readable
    ? selected.value
    : null
)

function remember(nodes: TreeNode[]) {
  for (const node of nodes) nodesById.value.set(node.id, node)
}

watch(
  () => props.modelValue,
  async (open) => {
    if (!open || !props.connector) return
    roots.value = []
    expanded.value = []
    nodesById.value = new Map()
    selectedId.value = null
    error.value = ""
    loading.value = true
    try {
      roots.value = toTreeNodes(await loadChildren(props.connector.id, null))
      remember(roots.value)
    } catch (cause) {
      error.value = messageOf(cause, "Could not read the catalog")
    } finally {
      loading.value = false
    }
  }
)

// The node an action is aimed at: the selected one, or the root of the
// connector when nothing is selected.
const targetLabel = computed(() => selected.value?.label ?? "Whole connection")

/**
 * Re-read one branch after something changed it.
 *
 * Invalidating the query is not enough on its own: QTree keeps the children on
 * the node object, so they have to be put back as well.
 */
async function reload(nodeId: string | null) {
  if (!props.connector) return
  const node = nodeId === null ? null : (nodesById.value.get(nodeId) ?? null)
  const previous = node ? (node.children ?? []) : roots.value

  const wasHere = previous.some((child) => child.id === selectedId.value)
  const children = toTreeNodes(await loadChildren(props.connector.id, nodeId))
  remember(children)

  if (node) {
    node.children = children
    node.lazy = false
    if (!expanded.value.includes(node.id)) expanded.value = [...expanded.value, node.id]
  } else {
    roots.value = children
  }

  // A selection that was removed by the action must not linger: it would name
  // a node that is no longer there.
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
  if (!props.connector) return fail()
  try {
    const children = toTreeNodes(await loadChildren(props.connector.id, node.id))
    remember(children)
    done(children)
  } catch (cause) {
    error.value = messageOf(cause, "Could not read the catalog")
    fail()
  }
}
</script>

<template>
  <AppDialog
    :model-value="modelValue"
    size="lg"
    :title="connector?.name"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection scroll>
      <AppBanner
        v-if="error"
        tone="error"
        class="q-mb-md"
        data-testid="catalog-error"
      >
        {{ error }}
      </AppBanner>

      <ActionBar
        v-if="connector && !loading"
        :connector-id="connector.id"
        :node-id="selectedId"
        :node-label="targetLabel"
        @done="reload"
      />

      <AppSpinner v-if="loading" />

      <!-- QTree has no caption prop, so the header is rendered here: the
           default header would show the label alone and silently drop the
           data type and row estimate. -->
      <q-tree
        v-else-if="roots.length"
        v-model:expanded="expanded"
        v-model:selected="selectedId"
        :nodes="roots"
        node-key="id"
        data-testid="catalog-tree"
        @lazy-load="onLazyLoad"
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
      </q-tree>

      <AppEmptyState
        v-else-if="!error"
        text="Nothing to show"
      />
    </AppSection>

    <AppSection
      v-if="selectedOpaque"
      divided
      data-testid="opaque-file"
    >
      <AppEmptyState :text="`${selectedOpaque.label} cannot be read as rows.`" />
    </AppSection>

    <AppSection
      v-if="selectedRelation && connector"
      divided
      scroll
    >
      <div class="text-subtitle2 q-mb-sm">
        {{ selectedRelation.label }}
      </div>
      <RowGrid
        :connector-id="connector.id"
        :node-id="selectedRelation.id"
        :row-estimate="selectedRelation.rowEstimate"
      />
    </AppSection>

    <template #actions>
      <AppButton
        variant="quiet"
        label="Close"
        @click="emit('update:modelValue', false)"
      />
    </template>
  </AppDialog>
</template>
