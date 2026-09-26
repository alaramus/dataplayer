<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query"
import { computed, onBeforeUnmount, shallowRef, watch } from "vue"

import { ConnectorsService } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { useCurrentUser } from "@/shared/auth/currentUser"
import GraphViewer from "@/shared/graph/GraphViewer.vue"
import { emptyGraphView, parseGraphView, serializeGraphView } from "@/shared/graph/viewState"
import { serverStorageKey } from "@/shared/servers/context"
import {
  AppBanner,
  AppButton,
  AppCardFrame,
  AppCardHead,
  AppEmptyState,
  AppIconButton,
  AppSpinner,
  appIcons,
  useToast,
} from "@/shared/ui"

import { endsOf, mapGraph } from "./model"

/**
 * What the connections can give each other, all of them at once (D174).
 *
 * A space of the rail's switch rather than a tab of the data workspace: it is
 * about every connection, not one. What it opens — a catalog, a pair — opens
 * in Data, which the page shows again.
 */
const emit = defineEmits<{
  openCatalog: [connectorId: string]
  openPair: [sourceId: string, destinationId: string]
}>()

const toast = useToast()
const me = useCurrentUser()
const answer = useQuery({
  queryKey: ["interaction-map"],
  queryFn: async () => (await ConnectorsService.readInteractionMap()).data,
  retry: false,
})
const graph = computed(() => (answer.data.value ? mapGraph(answer.data.value) : null))
const empty = computed(() => answer.data.value?.connections.length === 0)

const view = shallowRef(emptyGraphView())
const storageKey = computed(() =>
  me.data.value ? serverStorageKey(`dataplayer-interaction-map:${me.data.value.id}`) : null
)
let saveTimer: ReturnType<typeof setTimeout> | undefined
let storageReported = false

function storageFailed() {
  if (storageReported) return
  storageReported = true
  toast.error("The map's layout could not be saved in this browser")
}
watch(storageKey, (key) => {
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
onBeforeUnmount(() => {
  if (saveTimer !== undefined) clearTimeout(saveTimer)
  save()
})

function openPair(edgeId: string) {
  const ends = answer.data.value ? endsOf(answer.data.value, edgeId) : null
  if (ends !== null) emit("openPair", ends.source, ends.destination)
}

// No first panel to hide: the header's button is not drawn over this space.
defineExpose({ hasFirstPanel: false, toggleFirstPanel: () => undefined, firstPanelCollapsed: false })
</script>

<template>
  <div
    class="interaction-map"
    data-testid="interaction-map"
  >
    <!-- The card every space draws: its frame, and a head of the same height
         and ground as a Data section's tab strip. -->
    <AppCardFrame
      tag="section"
      class="interaction-map__card"
    >
      <AppCardHead title="Connections map">
        <template #actions>
          <AppIconButton
            :icon="appIcons.refresh"
            tooltip="Read the connections again"
            data-testid="interaction-map-reload"
            :loading="answer.isFetching.value"
            @click="answer.refetch()"
          />
        </template>
      </AppCardHead>
      <div
        v-if="answer.isPending.value"
        class="interaction-map__center"
      >
        <AppSpinner />
      </div>
      <AppBanner
        v-else-if="answer.isError.value"
        tone="error"
      >
        {{ messageOf(answer.error.value, "The map could not be read") }}
      </AppBanner>
      <div
        v-else-if="empty"
        class="interaction-map__center"
      >
        <AppEmptyState
          :icon="appIcons.hub"
          text="No connection is switched on yet."
        />
      </div>
      <GraphViewer
        v-else-if="graph"
        v-model="view"
        :graph="graph"
        class="interaction-map__viewer"
        @activate="emit('openCatalog', $event)"
      >
        <template #node-actions="{ node }">
          <AppButton
            variant="quiet"
            size="sm"
            :icon="appIcons.folder"
            label="Open catalog"
            data-testid="interaction-map-open-catalog"
            @click="emit('openCatalog', node.id)"
          />
        </template>
        <template #edge-actions="{ edge }">
          <AppButton
            variant="quiet"
            size="sm"
            :icon="appIcons.swapSides"
            label="Open as pair"
            data-testid="interaction-map-open-pair"
            @click="openPair(edge.id)"
          />
        </template>
      </GraphViewer>
    </AppCardFrame>
  </div>
</template>

<style scoped>
.interaction-map {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
}
.interaction-map__card {
  flex: 1;
}
.interaction-map__center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.interaction-map__viewer {
  flex: 1;
  min-height: 0;
}
</style>
