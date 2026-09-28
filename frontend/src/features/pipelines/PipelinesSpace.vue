<script setup lang="ts">
import { computed, ref, useTemplateRef, watch } from "vue"

import type { ConnectorPublic } from "@/client"
import ConnectorIcon from "@/features/connectors/ConnectorIcon.vue"
import ConnectorList from "@/features/connectors/ConnectorList.vue"
import { useConnectors } from "@/features/connectors/api"
import ConnectorsHead from "@/features/workspace/panels/ConnectorsHead.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { serverStorageKey } from "@/shared/servers/context"
import {
  AppButton,
  AppCardFrame,
  AppCardHead,
  AppEmptyState,
  AppIconButton,
  AppScrollArea,
  AppSpinner,
  appIcons,
  useToast,
} from "@/shared/ui"
import { WorkspaceSeparator } from "@/shared/workspace"
import { useSideRail } from "@/shared/workspace/useSideRail"

import { useCreatePipeline, usePipelines } from "./api"
import { CONNECTION_DRAG, newPipelineName } from "./model"
import PipelineView from "./PipelineView.vue"

/**
 * The pipelines space (D175): the connections on the left, to be dragged onto
 * the canvas of the pipeline chosen on the right.
 */
const toast = useToast()
const workspace = useWorkspaceActions()
const connectors = useConnectors()
const pipelines = usePipelines()
const creating = useCreatePipeline()
const view = useTemplateRef<InstanceType<typeof PipelineView>>("view")

const SELECTED_KEY = "dataplayer-pipeline"

function storedSelection(): string | null {
  try {
    return localStorage.getItem(serverStorageKey(SELECTED_KEY))
  } catch {
    return null
  }
}

const selectedId = ref<string | null>(storedSelection())
const current = computed(() => {
  const list = pipelines.data.value ?? []
  return list.find((one) => one.id === selectedId.value) ?? list[0] ?? null
})

watch(current, (pipeline) => {
  try {
    if (pipeline !== null) localStorage.setItem(serverStorageKey(SELECTED_KEY), pipeline.id)
  } catch {
    // Remembering which one was open is a courtesy.
  }
})

async function createPipeline() {
  try {
    const made = await creating.mutateAsync(newPipelineName((pipelines.data.value ?? []).length))
    selectedId.value = made.id
  } catch (cause) {
    toast.error(messageOf(cause, "The pipeline could not be created"))
  }
}

const rows = computed(() => connectors.data.value?.data ?? [])
// The list of connections is the one Data shows, head, filter and all, so
// switching between the two spaces leaves that card as it was.
const shownRows = computed(() => {
  const query = workspace.connectorNameFilter.value.trim().toLocaleLowerCase()
  return query ? rows.value.filter((one) => one.name.toLocaleLowerCase().includes(query)) : rows.value
})

// The same re-read the column of connections registers. Here too, because a
// session opened on this space has not drawn that column yet.
useReloadable("connectors", async () => {
  await connectors.refetch()
})

function place(connector: ConnectorPublic) {
  if (current.value === null) {
    toast.info("Create a pipeline first, then place connections on it")
    return
  }
  view.value?.place(connector.id)
}

function startDrag(event: DragEvent, connector: ConnectorPublic) {
  if (event.dataTransfer === null) return
  event.dataTransfer.setData(CONNECTION_DRAG, connector.id)
  event.dataTransfer.setData("text/plain", connector.name)
  event.dataTransfer.effectAllowed = "copy"
}

const spaceElement = ref<HTMLElement | null>(null)
const { narrow, shownWidth, resize, pressGap } = useSideRail(spaceElement, {
  width: serverStorageKey("dataplayer-pipelines-rail"),
  narrow: serverStorageKey("dataplayer-pipelines-rail-narrow"),
})

// The header button collapses the first panel of the space being shown
// through one shape; here that is the list of connections.
defineExpose({
  toggleFirstPanel: () => { narrow.value = !narrow.value },
  firstPanelCollapsed: computed(() => narrow.value),
})
</script>

<template>
  <div
    ref="spaceElement"
    class="pipelines"
    data-testid="pipelines-space"
  >
    <AppCardFrame
      tag="aside"
      class="pipelines__rail"
      :style="{ flexBasis: `${String(shownWidth)}px` }"
      data-testid="pipelines-rail"
    >
      <!-- The pushed-aside column of connections as Data draws it
           (ConnectorRail), so the switch between the spaces moves nothing:
           the plus alone in a head, and the icons under it scrolled under a
           bar that takes no room. The header button brings the names back. -->
      <template v-if="narrow">
        <AppCardHead class="pipelines__narrow-head">
          <AppIconButton
            :icon="appIcons.add"
            tooltip="New connection"
            data-testid="add-connector"
            @click="workspace.editConnector(null)"
          />
        </AppCardHead>
        <AppScrollArea>
          <div class="pipelines__icons">
            <span
              v-for="connector in rows"
              :key="connector.id"
              draggable="true"
              @dragstart="startDrag($event, connector)"
            >
              <ConnectorIcon
                :connector-id="connector.id"
                :name="connector.name"
                :adapter-type="connector.adapter_type"
                :enabled="connector.enabled"
                :tooltip="connector.name"
                :testid="`pipelines-rail-${connector.name}`"
                @click="place(connector)"
              />
            </span>
          </div>
        </AppScrollArea>
      </template>
      <template v-else>
        <AppCardHead>
          <ConnectorsHead class="pipelines__head" />
        </AppCardHead>
        <div class="pipelines__connections">
          <ConnectorList
            :rows="shownRows"
            :loading="connectors.isLoading.value"
            :empty-text="workspace.connectorNameFilter.value.trim() ? 'No matching connections' : undefined"
            :drag-type="CONNECTION_DRAG"
            @open="place"
            @edit="workspace.editConnector($event.id)"
          />
        </div>
      </template>
    </AppCardFrame>

    <WorkspaceSeparator
      direction="row"
      @move="resize"
      @toggle="pressGap"
    />

    <AppCardFrame
      tag="section"
      class="pipelines__main"
    >
      <PipelineView
        v-if="current"
        ref="view"
        :key="current.id"
        :pipeline-id="current.id"
        :pipelines="pipelines.data.value ?? []"
        :connections="rows"
        :creating="creating.isPending.value"
        @select="(id) => (selectedId = id)"
        @create="createPipeline"
        @deleted="selectedId = null"
      />
      <template v-else>
        <AppCardHead title="Pipelines" />
        <div
          v-if="pipelines.isPending.value"
          class="pipelines__center"
        >
          <AppSpinner />
        </div>
        <div
          v-else-if="pipelines.isError.value"
          class="pipelines__center"
        >
          <AppEmptyState
            icon="error"
            :text="messageOf(pipelines.error.value, 'Pipelines could not be read')"
          />
        </div>
        <div
          v-else
          class="pipelines__center pipelines__center--stacked"
        >
          <span>No pipelines yet.</span>
          <AppButton
            :icon="appIcons.add"
            label="Create a pipeline"
            :loading="creating.isPending.value"
            data-testid="pipeline-create-first"
            @click="createPipeline"
          />
        </div>
      </template>
    </AppCardFrame>
  </div>
</template>

<style scoped>
/* No gap of its own: the separator between the two cards is that gap, and
   the handle that resizes them, as it is between workspace columns (D12). */
.pipelines {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
}
.pipelines__rail {
  flex-grow: 0;
  flex-shrink: 0;
}
.pipelines__main {
  flex: 1;
}
.pipelines__head {
  flex: 1;
  min-width: 0;
}
.pipelines__rail .pipelines__narrow-head {
  justify-content: center;
  margin-bottom: var(--dp-space-1);
  padding: 0;
}
.pipelines__connections {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-top: var(--dp-space-1);
}
.pipelines__icons {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-bottom: var(--dp-space-half);
}
.pipelines__center {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--dp-text-muted);
}
.pipelines__center--stacked {
  flex-direction: column;
  gap: var(--dp-space-3);
}
</style>
