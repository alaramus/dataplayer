<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { MetricsCatalog } from "@/client"
import { AppButton, AppEmptyState, AppTree } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { catalogTree, tickedSeries } from "./catalog"
import type { SeriesEntry } from "./catalog"
import { draftsFor } from "./widgetSpecs"
import type { WidgetDraft } from "./widgetSpecs"

/**
 * The one way to put something on a dashboard: tick what to draw. There is no
 * widget type to choose — the ticks decide it (`widgetSpecs.ts`).
 */
const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  catalog: MetricsCatalog | undefined
  index: Map<number, SeriesEntry>
  room: number
}>()

const emit = defineEmits<{ add: [drafts: WidgetDraft[]]; agents: [] }>()

const ticked = ref<string[]>([])
const expanded = ref<string[]>([])
const nodes = computed(() => catalogTree(props.catalog))

// Agents and hosts open, metrics shut: a host is where one starts looking.
// Also for branches that arrive after the window opened — the catalog may
// still be on its way — but never again for one somebody has since closed.
const opened = new Set<string>()

function openBranches() {
  const fresh = nodes.value
    .flatMap((agent) => [String(agent.key), ...(agent.children ?? []).map((host) => String(host.key))])
    .filter((key) => !opened.has(key))
  for (const key of fresh) opened.add(key)
  if (fresh.length > 0) expanded.value = [...expanded.value, ...fresh]
}

watch(open, (isOpen) => {
  if (!isOpen) return
  ticked.value = []
  expanded.value = []
  opened.clear()
  openBranches()
})

watch(nodes, () => {
  if (open.value) openBranches()
})

const drafts = computed(() =>
  draftsFor(
    tickedSeries(ticked.value)
      .map((id) => props.index.get(id))
      .filter((entry): entry is SeriesEntry => entry !== undefined)
  )
)

const summary = computed(() => {
  const count = drafts.value.length
  if (count === 0) return "Tick the series to draw"
  const widgets = `${String(count)} widget${count === 1 ? "" : "s"}`
  return count > props.room ? `${widgets}; ${String(props.room)} fit on this dashboard` : widgets
})

function add() {
  emit("add", drafts.value)
  open.value = false
}
</script>

<template>
  <WindowDialog
    v-model="open"
    title="Add widgets"
    size="lg"
    data-testid="add-widgets"
  >
    <AppEmptyState
      v-if="nodes.length === 0 || nodes.every((agent) => (agent.children ?? []).length === 0)"
      icon="sensors_off"
      text="No agent has reported anything yet. Register one and start it with the key it is given."
    />
    <AppTree
      v-else
      v-model:expanded="expanded"
      v-model:ticked="ticked"
      :nodes="nodes"
      :selected="null"
      node-key="key"
      tickable
      data-testid="add-widgets-tree"
    >
      <template #default-header="{ node }">
        <span>{{ node.label }}</span>
        <span
          v-if="node.caption"
          class="add-widgets__unit"
        >{{ node.caption }}</span>
      </template>
    </AppTree>

    <template #actions>
      <span class="add-widgets__summary">{{ summary }}</span>
      <AppButton
        variant="quiet"
        label="Agents"
        icon="sensors"
        @click="emit('agents')"
      />
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="open = false"
      />
      <AppButton
        label="Add"
        :disable="drafts.length === 0 || room === 0"
        data-testid="add-widgets-confirm"
        @click="add"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.add-widgets__unit {
  margin-left: var(--dp-space-2);
  color: var(--dp-text-muted);
}

.add-widgets__summary {
  margin-right: auto;
  color: var(--dp-text-muted);
}
</style>
