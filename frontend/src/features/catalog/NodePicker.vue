<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import type { FetchColumn } from "@/client"
import { isReadableNode, roleOf } from "@/features/catalog/nodes"
import type { CatalogNode, PickedNode } from "@/features/catalog/nodes"
import { useConnectors } from "@/features/connectors/api"
import { messageOf } from "@/shared/api/errors"
import { AppButton, AppEmptyState, AppFormControl, AppSelect, AppSpinner } from "@/shared/ui"

/**
 * Pick a node in one of your connections, and read what it calls its columns.
 *
 * One walk of one catalog, shared by everything that has to name a node
 * somewhere else: bringing rows in from another source (D43) and drawing a
 * reference to one (D106) ask the same question, and asking it twice would be
 * two answers to what a leaf is and which of them may be read.
 */
const props = defineProps<{
  /** What every control here is found by. The caller owns its own names. */
  testid: string
  label?: string
}>()
const emit = defineEmits<{
  pick: [value: PickedNode | null]
  /** Why the walk stopped, for the one banner the dialog already has. */
  trouble: [message: string]
}>()

const connectors = useConnectors()
const sourceId = ref("")
const trail = ref<CatalogNode[]>([])
const nodes = ref<CatalogNode[]>([])
const browsing = ref(false)
const chosen = ref<CatalogNode | null>(null)

const sources = computed(() =>
  (connectors.data.value?.data ?? [])
    .filter((connector) => connector.enabled)
    .map((connector) => ({ label: connector.name, value: connector.id }))
)

const connection = computed(() =>
  (connectors.data.value?.data ?? []).find((connector) => connector.id === sourceId.value)
)

async function openLevel(node: CatalogNode | null): Promise<boolean> {
  if (sourceId.value === "") return false
  browsing.value = true
  emit("trouble", "")
  try {
    const answer = await ConnectorsService.readCatalog({
      path: { connector_id: sourceId.value },
      query: node === null ? {} : { node_id: node.id },
    })
    nodes.value = answer.data
    return true
  } catch (error) {
    emit("trouble", messageOf(error, "Could not read that source"))
    return false
  } finally {
    browsing.value = false
  }
}

watch(sourceId, async () => {
  trail.value = []
  chosen.value = null
  emit("pick", null)
  await openLevel(null)
})

async function step(node: CatalogNode) {
  if (roleOf(node) === "leaf") {
    if (isReadableNode(node)) await choose(node)
    return
  }
  if (await openLevel(node)) trail.value = [...trail.value, node]
}

/**
 * One step back: a chosen node is let go first, and its level is still the one
 * on screen. Walking up while a node stayed chosen emptied the trail, took Back
 * away and kept the list hidden, so the only way out was another source.
 */
async function back() {
  if (chosen.value !== null) {
    chosen.value = null
    emit("trouble", "")
    emit("pick", null)
    return
  }
  const shorter = trail.value.slice(0, -1)
  if (await openLevel(shorter.at(-1) ?? null)) trail.value = shorter
}

/** The node's own columns, read the way any other page of it is read. */
async function choose(node: CatalogNode) {
  chosen.value = node
  emit("trouble", "")
  const source = connection.value
  if (source === undefined) return
  let columns: FetchColumn[] = []
  try {
    const answer = await ConnectorsService.fetchRows({
      path: { connector_id: sourceId.value },
      body: { node_id: node.id, limit: 1 },
    })
    columns = answer.data.columns
  } catch (error) {
    emit("trouble", messageOf(error, "Could not read that source as rows"))
  }
  emit("pick", {
    connectorId: source.id,
    connectorName: source.name,
    adapterType: source.adapter_type,
    node,
    columns,
  })
}

const here = computed(() => {
  const path = chosen.value === null ? trail.value : [...trail.value, chosen.value]
  return path.length === 0 ? "Pick a node" : path.map((node) => node.name).join(" / ")
})
</script>

<template>
  <AppSelect
    :model-value="sourceId"
    :options="sources"
    :label="props.label ?? 'Source'"
    :loading="connectors.isFetching.value"
    :data-testid="`${props.testid}-source`"
    @update:model-value="sourceId = String($event)"
  />

  <AppFormControl
    v-if="sourceId !== ''"
    class="node-picker"
  >
    <div class="node-picker__where">
      <AppButton
        v-if="trail.length > 0 || chosen !== null"
        label="Back"
        variant="quiet"
        size="sm"
        :icon="appIcons.arrowBack"
        :data-testid="`${props.testid}-back`"
        @click="back"
      />
      <span :data-testid="`${props.testid}-where`">{{ here }}</span>
    </div>
    <AppSpinner v-if="browsing" />
    <ul
      v-else-if="chosen === null"
      class="node-picker__nodes"
    >
      <li
        v-for="node in nodes"
        :key="node.id"
      >
        <AppButton
          :label="node.name"
          variant="quiet"
          layout="navigation"
          size="sm"
          :disable="roleOf(node) === 'leaf' && !isReadableNode(node)"
          :data-testid="`${props.testid}-node-${node.name}`"
          @click="step(node)"
        />
      </li>
    </ul>
    <AppEmptyState
      v-if="!browsing && chosen === null && nodes.length === 0"
      text="Nothing here"
    />
  </AppFormControl>
</template>

<style scoped>
.node-picker {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}
.node-picker__where {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  min-height: var(--dp-form-control-height);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
.node-picker__nodes {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 180px;
  overflow: auto;
}
</style>
