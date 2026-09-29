<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref, watch } from "vue"

import type { MetricsCatalog } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { AppButton, AppEmptyState, AppSpinner, AppTree } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { usePresets } from "./api"
import type { PresetTarget } from "./api"
import { catalogTree, connectorOfKey, hostOfKey, tickedProcesses, tickedSeries } from "./catalog"
import type { SeriesEntry } from "./catalog"
import type { Widget } from "./dashboardModel"
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

const emit = defineEmits<{ add: [drafts: WidgetDraft[]]; addPreset: [widgets: Widget[]]; agents: [] }>()

const ticked = ref<string[]>([])
// Ticks say what to draw; the row selected says which host's ready-made
// layouts to offer. Two questions asked of one tree.
const selected = ref<string | null>(null)
const target = computed<PresetTarget | null>(() => {
  const host = hostOfKey(selected.value)
  if (host !== null) return { kind: "host", ...host, label: host.host }
  const connectorId = connectorOfKey(selected.value)
  if (connectorId === null) return null
  const connector = props.catalog?.connectors?.find((one) => one.connector_id === connectorId)
  return connector === undefined ? null : { kind: "connector", connectorId, label: connector.name }
})
const presets = usePresets(target)
// Every source starts shut; the one wanted is opened by its name.
const expanded = ref<string[]>([])
const nodes = computed(() => catalogTree(props.catalog))

watch(open, (isOpen) => {
  if (!isOpen) return
  ticked.value = []
  selected.value = null
  expanded.value = []
})

// A name pressed opens its branch as well as selecting it, so a shut tree is
// walked by the names and not only by the small arrows beside them.
watch(selected, (key) => {
  if (key !== null && !expanded.value.includes(key)) expanded.value = [...expanded.value, key]
})

const drafts = computed(() =>
  draftsFor(
    tickedSeries(ticked.value)
      .map((id) => props.index.get(id))
      .filter((entry): entry is SeriesEntry => entry !== undefined),
    tickedProcesses(ticked.value)
  )
)

function addPreset(widgets: Widget[]) {
  emit("addPreset", widgets)
  open.value = false
}

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
    size="wide-form"
    sizing="stable"
    data-testid="add-widgets"
  >
    <!-- A list rather than a form, so it brings the window's margin itself:
         its first line stood against the frame. -->
    <div class="add-widgets">
      <AppEmptyState
        v-if="nodes.length === 0 || nodes.every((source) => (source.children ?? []).length === 0)"
        icon="sensors_off"
        text="Nothing has reported anything yet. Register an agent, or switch a connection's reporting on, in Sources."
      />
      <div
        v-else
        class="add-widgets__presets"
        data-testid="add-widgets-presets"
      >
        <span
          v-if="target === null"
          class="add-widgets__hint"
        >Select a host or a connection to see its ready-made layouts, or tick what to draw.</span>
        <AppSpinner v-else-if="presets.isPending.value" />
        <span
          v-else-if="presets.isError.value"
          class="add-widgets__hint"
        >{{ messageOf(presets.error.value, "The layouts could not be read") }}</span>
        <template v-else>
          <div
            v-for="preset in presets.data.value ?? []"
            :key="preset.key"
            class="add-widgets__preset"
          >
            <div class="add-widgets__preset-text">
              <span>{{ preset.name }} for {{ target.label }}</span>
              <span class="add-widgets__hint">{{ preset.description }} {{ preset.widgets.length }} of {{ preset.total }} widgets.</span>
            </div>
            <AppButton
              variant="secondary"
              size="sm"
              :icon="appIcons.dashboardCustomize"
              label="Add layout"
              :disable="preset.widgets.length === 0 || room === 0"
              :data-testid="`add-preset-${preset.key}`"
              @click="addPreset(preset.widgets)"
            />
          </div>
        </template>
      </div>
      <AppTree
        v-if="nodes.length > 0"
        v-model:expanded="expanded"
        v-model:ticked="ticked"
        v-model:selected="selected"
        :nodes="nodes"
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
    </div>

    <template #actions>
      <span class="add-widgets__summary">{{ summary }}</span>
      <AppButton
        variant="quiet"
        label="Sources"
        :icon="appIcons.sensors"
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
.add-widgets {
  padding: var(--dp-space-2) var(--dp-space-4);
}
.add-widgets__presets {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  padding-bottom: var(--dp-space-2);
  margin-bottom: var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
}

.add-widgets__preset {
  display: flex;
  align-items: center;
  gap: var(--dp-space-3);
}

.add-widgets__preset-text {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.add-widgets__hint {
  color: var(--dp-text-muted);
}

.add-widgets__unit {
  margin-left: var(--dp-space-2);
  color: var(--dp-text-muted);
}

.add-widgets__summary {
  margin-right: auto;
  padding-left: var(--dp-space-2);
  color: var(--dp-text-muted);
}
</style>
