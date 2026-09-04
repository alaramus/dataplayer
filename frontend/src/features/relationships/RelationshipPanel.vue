<script setup lang="ts">
import { useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue"

import { ConnectorsService } from "@/client"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { serverStorageKey } from "@/shared/servers/context"
import { useCurrentUser } from "@/shared/auth/currentUser"
import GraphViewer from "@/shared/graph/GraphViewer.vue"
import { emptyGraphView, parseGraphView, serializeGraphView } from "@/shared/graph/viewState"
import { AppBanner, AppButton, AppIconButton, AppProgress, useToast } from "@/shared/ui"
import { useSourceChangesStore } from "@/stores/sourceChanges"
import { GraphLoadError, loadRelations } from "./load"
import { relationGraph } from "./model"
import type { DiagramNodeRef } from "./model"

const props = defineProps<{ panelId: string; connectorId: string; connectorName: string; adapterType: string; nodes: DiagramNodeRef[] }>()
const workspace = useWorkspaceActions()
const client = useQueryClient()
const toast = useToast()
const me = useCurrentUser()
const loaded = ref(0)
const cancelled = ref(false)
const view = shallowRef(emptyGraphView())
const queryKey = computed(() => ["relationshipGraph", props.connectorId, props.nodes.map((node) => node.id).sort()])
const source = useQuery({
  queryKey,
  queryFn: async ({ signal }) => {
    loaded.value = 0; cancelled.value = false
    return loadRelations(props.nodes, async (nodeId, readSignal) => (
      await ConnectorsService.readRelationModel({ path: { connector_id: props.connectorId }, query: { node_id: nodeId }, signal: readSignal })
    ).data, signal, (count) => { loaded.value = count })
  },
  staleTime: 5 * 60_000,
  retry: false,
})
const graph = computed(() => source.data.value ? relationGraph(source.data.value) : null)
const loadError = computed(() => source.error.value instanceof GraphLoadError
  ? source.error.value.message : messageOf(source.error.value, "Could not load the diagram"))
const modelOf = (id: string) => source.data.value?.models.find((model) => model.node_id === id)
const storageKey = computed(() => me.data.value ? serverStorageKey(`dataplayer-graph:${me.data.value.id}:${props.panelId}`) : null)
let saveTimer: ReturnType<typeof setTimeout> | undefined
let storageReported = false

function storageFailed() {
  if (storageReported) return
  storageReported = true
  toast.error("The graph layout could not be saved in this browser")
}
watch(storageKey, (key) => {
  if (saveTimer !== undefined) clearTimeout(saveTimer)
  if (!key) return
  try { view.value = parseGraphView(localStorage.getItem(key)) ?? emptyGraphView() }
  catch { storageFailed() }
}, { immediate: true })
function save() {
  if (!storageKey.value) return
  try { localStorage.setItem(storageKey.value, serializeGraphView(view.value)) }
  catch { storageFailed() }
}
watch(view, () => {
  if (saveTimer !== undefined) clearTimeout(saveTimer)
  saveTimer = setTimeout(save, 200)
})
window.addEventListener("pagehide", save)
onBeforeUnmount(() => {
  window.removeEventListener("pagehide", save)
  if (saveTimer !== undefined) clearTimeout(saveTimer)
  save()
})
useReloadable(props.panelId, async () => { await source.refetch() })
const changes = useSourceChangesStore()
watch(() => changes.lastChange(props.connectorId), (at, before) => { if (at && at !== before) void source.refetch() })

async function cancel() { cancelled.value = true; await client.cancelQueries({ queryKey: queryKey.value, exact: true }) }
function openTable(id: string) {
  const model = modelOf(id)
  if (!model) { workspace.revealInCatalog(props.connectorId, id, id); return }
  workspace.openRows({ connectorId: props.connectorId, connectorName: props.connectorName, adapterType: props.adapterType, nodeId: model.node_id, title: model.name, describable: true })
}
function openStructure(id: string) {
  const model = modelOf(id)
  if (model) workspace.openStructure({ connectorId: props.connectorId, connectorName: props.connectorName, adapterType: props.adapterType, nodeId: model.node_id, title: model.name })
}
</script>

<template>
  <div
    class="relationship-panel"
    data-testid="relationship-panel"
  >
    <!-- No line naming the scope and no line explaining the arrows: the tab
         already says which connection this is and how many tables were asked
         for, and a placeholder card says on its own face whether it is outside
         the selection or unreadable. Two standing bars for that took height
         from the only thing here that needs it. -->
    <div
      v-if="source.isFetching.value"
      class="relationship-panel__loading"
      role="status"
    >
      <span>Reading structure {{ loaded }} / {{ nodes.length }}</span>
      <AppProgress
        label="Reading table structures"
        :value="nodes.length ? loaded / nodes.length : 0"
      />
      <AppIconButton
        icon="stop"
        tooltip="Stop loading"
        @click="cancel"
      />
    </div>
    <AppBanner
      v-if="source.error.value"
      tone="error"
    >
      {{ loadError }}
    </AppBanner>
    <AppBanner
      v-if="cancelled"
      tone="info"
    >
      Loading stopped. Reload to read the selection again.
    </AppBanner>
    <AppBanner
      v-if="source.data.value?.failures.length"
      tone="warning"
    >
      {{ source.data.value.failures.length }} structures could not be read. Select a dashed node for details.
    </AppBanner>
    <GraphViewer
      v-if="graph"
      v-model="view"
      :graph="graph"
      class="relationship-panel__viewer"
      @activate="openTable"
    >
      <template #node-actions="{ node }">
        <template v-if="modelOf(node.id)">
          <AppButton
            variant="quiet"
            size="sm"
            icon="table_chart"
            label="Open table"
            data-testid="graph-open-table"
            @click="openTable(node.id)"
          />
          <AppButton
            variant="quiet"
            size="sm"
            icon="account_tree"
            label="Structure"
            @click="openStructure(node.id)"
          />
        </template>
        <AppButton
          v-else
          variant="quiet"
          size="sm"
          icon="my_location"
          label="Show in catalog"
          @click="openTable(node.id)"
        />
      </template>
    </GraphViewer>
  </div>
</template>

<style scoped>
.relationship-panel { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.relationship-panel__loading { display: flex; align-items: center; gap: 12px; padding: 3px 8px; font-size: 12px; border-bottom: 1px solid var(--dp-border); }
.relationship-panel__loading > span { white-space: nowrap; }
.relationship-panel__viewer { flex: 1; min-height: 0; }
</style>
