<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, onBeforeUnmount, ref, shallowRef, watch } from "vue"

import { ConnectorsService, DeclaredReferencesService } from "@/client"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { serverStorageKey } from "@/shared/servers/context"
import { useCurrentUser } from "@/shared/auth/currentUser"
import GraphViewer from "@/shared/graph/GraphViewer.vue"
import { emptyGraphView, parseGraphView, serializeGraphView } from "@/shared/graph/viewState"
import { AppBanner, AppButton, AppIconButton, AppProgress, useToast } from "@/shared/ui"
import { useSourceChangesStore } from "@/stores/sourceChanges"
import { expandHolders, GraphLoadError, loadRelations, withDeclared } from "./load"
import { graphIdOf, relationGraph } from "./model"
import type { DiagramNodeRef } from "./model"

const props = defineProps<{ panelId: string; connectorId: string; connectorName: string; adapterType: string; nodes: DiagramNodeRef[] }>()
const workspace = useWorkspaceActions()
const client = useQueryClient()
const toast = useToast()
const me = useCurrentUser()
const loaded = ref(0)
const total = ref(props.nodes.length)
const cancelled = ref(false)
const view = shallowRef(emptyGraphView())
const queryKey = computed(() => ["relationshipGraph", props.connectorId, props.nodes.map((node) => node.id).sort()])
const source = useQuery({
  queryKey,
  queryFn: async ({ signal }) => {
    loaded.value = 0; cancelled.value = false
    const requested = await expandHolders(props.nodes, async (nodeId) => (
      await ConnectorsService.readCatalog({ path: { connector_id: props.connectorId }, query: { node_id: nodeId }, signal })
    ).data)
    total.value = requested.length
    const read = await loadRelations(requested, async (nodeId, readSignal) => (
      await ConnectorsService.readRelationModel({ path: { connector_id: props.connectorId }, query: { node_id: nodeId }, signal: readSignal })
    ).data, signal, (count) => { loaded.value = count })
    const references = (await DeclaredReferencesService.referencesListDeclaredReferences({
      query: { connector_id: props.connectorId }, signal,
    })).data
    return withDeclared(read, props.connectorId, references, async (end, readSignal) => (
      await ConnectorsService.readRelationModel({ path: { connector_id: end.connector_id }, query: { node_id: end.node_id }, signal: readSignal })
    ).data, signal)
  },
  staleTime: 5 * 60_000,
  retry: false,
})
const graph = computed(() => source.data.value ? relationGraph(source.data.value) : null)
const loadError = computed(() => source.error.value instanceof GraphLoadError
  ? source.error.value.message : messageOf(source.error.value, t("relationships.load_failed")))

/** Where a card's relation lives: this connection, or the far end of a declared reference. */
function placeOf(id: string) {
  const model = source.data.value?.models.find((one) => one.node_id === id)
  if (model) return { connectorId: props.connectorId, connectorName: props.connectorName, adapterType: props.adapterType, nodeId: model.node_id, label: model.name, model }
  const far = source.data.value?.far?.find((one) => graphIdOf(props.connectorId, one.connectorId, one.nodeId) === id)
  return far ? { ...far, label: far.model?.name ?? far.label } : null
}
const modelOf = (id: string) => placeOf(id)?.model ?? null
const storageKey = computed(() => me.data.value ? serverStorageKey(`dataplayer-graph:${me.data.value.id}:${props.panelId}`) : null)
let saveTimer: ReturnType<typeof setTimeout> | undefined
let storageReported = false

function storageFailed() {
  if (storageReported) return
  storageReported = true
  toast.error(t("relationships.layout_not_saved"))
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
useReloadable(() => props.panelId, async () => { await source.refetch() })
const changes = useSourceChangesStore()
watch(() => changes.lastChange(props.connectorId), (at, before) => { if (at && at !== before) void source.refetch() })

async function cancel() { cancelled.value = true; await client.cancelQueries({ queryKey: queryKey.value, exact: true }) }
function openTable(id: string) {
  const place = placeOf(id)
  if (!place?.model) { workspace.revealInCatalog(place?.connectorId ?? props.connectorId, place?.nodeId ?? id, place?.label ?? id); return }
  workspace.openRows({ connectorId: place.connectorId, connectorName: place.connectorName, adapterType: place.adapterType, nodeId: place.nodeId, title: place.label, describable: true })
}
function openStructure(id: string) {
  const place = placeOf(id)
  if (place?.model) workspace.openStructure({ connectorId: place.connectorId, connectorName: place.connectorName, adapterType: place.adapterType, nodeId: place.nodeId, title: place.label })
}
</script>

<template>
  <div
    class="relationship-panel"
    data-testid="relationship-panel"
  >
    <!-- Still no line naming the scope and none explaining the arrows: the tab
         already says which connection this is and how many tables were asked
         for, and a placeholder card says on its own face whether it is outside
         the selection or unreadable. What the panel offers about itself lives
         at the end of the graph toolbar's own row (D112) — and no way back to
         a catalog, because a diagram is drawn from several nodes at once and
         every node card carries its own way there. -->

    <div
      v-if="source.isFetching.value"
      class="relationship-panel__loading"
      role="status"
    >
      <span>{{ t("relationships.reading", { loaded, total }) }}</span>
      <AppProgress
        :label="t('relationships.reading_label')"
        :value="total ? loaded / total : 0"
      />
      <AppIconButton
        :icon="appIcons.stop"
        :tooltip="t('relationships.stop')"
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
      {{ t("relationships.stopped") }}
    </AppBanner>
    <AppBanner
      v-if="source.data.value?.failures.length"
      tone="warning"
    >
      {{ t("relationships.failures", { n: source.data.value.failures.length }, source.data.value.failures.length) }}
    </AppBanner>
    <GraphViewer
      v-if="graph"
      v-model="view"
      :graph="graph"
      class="relationship-panel__viewer"
      @activate="openTable"
    >
      <template #toolbar-end>
        <PanelCommands :panel-id="panelId" />
      </template>
      <template #node-actions="{ node }">
        <template v-if="modelOf(node.id)">
          <AppButton
            variant="quiet"
            size="sm"
            :icon="appIcons.tableChart"
            :label="t('relationships.open_table')"
            data-testid="graph-open-table"
            @click="openTable(node.id)"
          />
          <AppButton
            variant="quiet"
            size="sm"
            :icon="appIcons.accountTree"
            :label="t('relationships.structure')"
            @click="openStructure(node.id)"
          />
        </template>
        <AppButton
          v-else
          variant="quiet"
          size="sm"
          :icon="appIcons.myLocation"
          :label="t('relationships.show_in_catalog')"
          @click="openTable(node.id)"
        />
      </template>
    </GraphViewer>
  </div>
</template>

<style scoped>
.relationship-panel { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.relationship-panel__loading { display: flex; align-items: center; gap: var(--dp-space-3); padding: var(--dp-space-half) var(--dp-space-2); font-size: var(--dp-font-size-sm); border-bottom: 1px solid var(--dp-border); }
.relationship-panel__loading > span { white-space: nowrap; }
.relationship-panel__viewer { flex: 1; min-height: 0; }
</style>
