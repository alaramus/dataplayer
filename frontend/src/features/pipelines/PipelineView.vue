<script setup lang="ts">
import { useQueries, useQueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"
import { computed, onBeforeUnmount, ref, useTemplateRef, watch } from "vue"

import type { Card, CardRow, CardState, ConnectorPublic, PipelineSummary } from "@/client"
import { useAdapterTypes } from "@/features/connectors/api"
import { messageOf } from "@/shared/api/errors"
import Graph2D from "@/shared/graph/Graph2D.vue"
import type { Camera2, GraphSelection, Point2 } from "@/shared/graph/model"
import {
  AppBanner,
  AppButton,
  AppCardHead,
  AppEmptyState,
  AppForm,
  AppIconButton,
  AppInput,
  AppSelect,
  AppSpinner,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { cardStateKey, pipelineKey, readCardState, useDeletePipeline, usePipeline, useSavePipeline } from "./api"
import CardPickerWindow from "./CardPickerWindow.vue"
import {
  CONNECTION_DRAG,
  dropSpot,
  freeSpot,
  movedCard,
  pipelineGraph,
  positionsOf,
  withoutCard,
  withRows,
  worldPoint,
} from "./model"
import type { CardConnection } from "./model"

/**
 * One pipeline: its head, and the canvas of its cards (D175).
 *
 * The cards are held here as a draft and saved whole a moment after the last
 * change, with the version they were read at, as a dashboard is (D129).
 */
const props = defineProps<{
  pipelineId: string
  pipelines: readonly PipelineSummary[]
  connections: readonly ConnectorPublic[]
  creating: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  create: []
  deleted: []
}>()

const SAVE_DELAY_MS = 800
/** The server's bound on a pipeline (MAX_CARDS), said before a card is made. */
const MAX_CARDS = 50
const HOME: Camera2 = { x: 32, y: 32, zoom: 1 }

const toast = useToast()
const confirm = useConfirm()
const queryClient = useQueryClient()
const pipeline = usePipeline(() => props.pipelineId)
const saving = useSavePipeline()
const deleting = useDeletePipeline()
const adapterTypes = useAdapterTypes()

const name = ref("")
const version = ref(0)
const cards = ref<Card[]>([])
// The cards as the server last confirmed them: what a check is asked about.
const saved = ref<Card[]>([])
const camera = ref<Camera2 | null>(null)
const selection = ref<GraphSelection>(null)
const canvasBox = useTemplateRef<HTMLElement>("canvasBox")
const canvas = useTemplateRef<InstanceType<typeof Graph2D>>("canvas")

let timer: ReturnType<typeof setTimeout> | undefined
let pending = false
let inFlight = false

// Read, or read again after a conflict. Not while a change of this screen is
// waiting or on its way: the answer to that save is the newer one.
watch(
  () => pipeline.data.value,
  (read) => {
    if (read === undefined || pending || inFlight || read.version === version.value) return
    name.value = read.name
    version.value = read.version
    cards.value = [...(read.cards ?? [])]
    saved.value = cards.value
  },
  { immediate: true }
)

function schedule() {
  pending = true
  clearTimeout(timer)
  timer = setTimeout(() => void save(), SAVE_DELAY_MS)
}

async function save() {
  if (!pending || inFlight) return
  pending = false
  inFlight = true
  try {
    const answer = await saving.mutateAsync({
      id: props.pipelineId,
      body: { name: name.value, version: version.value, cards: cards.value },
    })
    version.value = answer.version
    saved.value = answer.cards ?? []
  } catch (cause) {
    if (cause instanceof AxiosError && cause.response?.status === 409) {
      toast.error("This pipeline was changed somewhere else; it has been read again")
      pending = false
      version.value = 0
      await queryClient.invalidateQueries({ queryKey: pipelineKey(props.pipelineId) })
      return
    }
    toast.error(messageOf(cause, "The pipeline could not be saved"))
  } finally {
    inFlight = false
    // A change made while the last one was on its way.
    if (pending) schedule()
  }
}

onBeforeUnmount(() => {
  clearTimeout(timer)
  void save()
})

const connectionsById = computed(
  () => new Map<string, CardConnection>(
    props.connections.map((one) => [one.id, { name: one.name, adapterType: one.adapter_type, enabled: one.enabled }])
  )
)
const typeTitles = computed(
  () => new Map((adapterTypes.data.value ?? []).map((type) => [type.name, type.title]))
)

const checks = useQueries({
  queries: computed(() =>
    saved.value.map((card) => ({
      queryKey: cardStateKey(props.pipelineId, card),
      queryFn: () => readCardState(props.pipelineId, card.id),
      staleTime: 60_000,
      retry: false,
    }))
  ),
})
const states = computed(() => {
  const found = new Map<string, CardState>()
  saved.value.forEach((card, index) => {
    const answer = checks.value[index]?.data
    if (answer !== undefined) found.set(card.id, answer)
  })
  return found
})

const graph = computed(() => pipelineGraph(cards.value, connectionsById.value, states.value, typeTitles.value))
const positions = computed(() => positionsOf(cards.value))
const switcher = computed(() => props.pipelines.map((one) => ({ label: one.name, value: one.id })))

function move(id: string, point: Point2) {
  cards.value = movedCard(cards.value, id, point)
  schedule()
}

// A card in the making: the window is open on its connection, and it is
// placed where it was dropped once something is ticked.
const picking = ref<{
  connectorId: string
  connectionName: string
  cardId: string | null
  rows: CardRow[] | null
  spot: Point2
  // Pressed rather than dropped: placed near the spot, clear of other cards.
  clear: boolean
} | null>(null)

function startCard(connectorId: string, spot: Point2, clear: boolean) {
  const connection = props.connections.find((one) => one.id === connectorId)
  if (connection === undefined) return
  if (!connection.enabled) {
    toast.error(`${connection.name} is switched off`)
    return
  }
  if (cards.value.length >= MAX_CARDS) {
    toast.error(`A pipeline holds at most ${String(MAX_CARDS)} cards`)
    return
  }
  picking.value = { connectorId, connectionName: connection.name, cardId: null, rows: null, spot, clear }
}

function over(event: DragEvent) {
  if (!event.dataTransfer?.types.includes(CONNECTION_DRAG)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = "copy"
}

function drop(event: DragEvent) {
  const connectorId = event.dataTransfer?.getData(CONNECTION_DRAG) ?? ""
  const box = canvasBox.value?.getBoundingClientRect()
  if (connectorId === "" || box === undefined) return
  event.preventDefault()
  const point = worldPoint(camera.value ?? HOME, { x: event.clientX - box.left, y: event.clientY - box.top })
  startCard(connectorId, dropSpot(point), false)
}

/** A connection pressed rather than dragged: its card goes to the middle of what is in view. */
function place(connectorId: string) {
  const box = canvasBox.value?.getBoundingClientRect()
  const middle = box === undefined ? { x: 0, y: 0 } : { x: box.width / 2, y: box.height / 2 }
  startCard(connectorId, dropSpot(worldPoint(camera.value ?? HOME, middle)), true)
}

function edit(cardId: string) {
  const card = cards.value.find((one) => one.id === cardId)
  if (card === undefined) return
  picking.value = {
    connectorId: card.connector_id,
    connectionName: connectionsById.value.get(card.connector_id)?.name ?? card.connector_name,
    cardId,
    rows: card.rows,
    spot: { x: card.x, y: card.y },
    clear: false,
  }
}

function picked(rows: CardRow[]) {
  const made = picking.value
  picking.value = null
  if (made === null) return
  if (made.cardId === null) {
    const spot = made.clear ? freeSpot(cards.value, made.spot, rows.length) : made.spot
    const card: Card = {
      id: crypto.randomUUID(),
      connector_id: made.connectorId,
      connector_name: made.connectionName,
      x: spot.x,
      y: spot.y,
      rows,
    }
    cards.value = [...cards.value, card]
    selection.value = { kind: "node", id: card.id }
  } else {
    cards.value = withRows(cards.value, made.cardId, rows)
  }
  schedule()
}

async function remove(cardId: string) {
  const card = graph.value.nodes.find((one) => one.id === cardId)
  const sure = await confirm({
    title: "Take this card off the pipeline?",
    message: `${card?.label ?? "The card"} and what is ticked on it leave this pipeline. Nothing in the connection changes.`,
    confirmLabel: "Take off",
  })
  if (!sure) return
  cards.value = withoutCard(cards.value, cardId)
  if (selection.value?.id === cardId) selection.value = null
  schedule()
}

const renameOpen = ref(false)
const renameDraft = ref("")

function startRename() {
  renameDraft.value = name.value
  renameOpen.value = true
}

function applyRename() {
  const next = renameDraft.value.trim()
  if (next === "") return
  renameOpen.value = false
  name.value = next
  schedule()
}

async function removePipeline() {
  const sure = await confirm({
    title: "Delete this pipeline?",
    message: `${name.value} and its ${String(cards.value.length)} cards will be removed. Nothing in the connections changes.`,
    confirmLabel: "Delete",
    danger: true,
  })
  if (!sure) return
  pending = false
  clearTimeout(timer)
  try {
    await deleting.mutateAsync(props.pipelineId)
    emit("deleted")
  } catch (cause) {
    toast.error(messageOf(cause, "The pipeline could not be deleted"))
  }
}

defineExpose({ place })
</script>

<template>
  <div
    class="pipeline-view"
    data-testid="pipeline-view"
  >
    <AppCardHead>
      <AppSelect
        class="pipeline-view__switcher"
        :model-value="pipelineId"
        :options="switcher"
        compact
        aria-label="Pipeline"
        data-testid="pipeline-switcher"
        @update:model-value="emit('select', String($event))"
      />
      <template #actions>
        <AppIconButton
          :icon="appIcons.centerFocusStrong"
          tooltip="Fit every card in view"
          data-testid="pipeline-fit"
          @click="canvas?.fit()"
        />
        <AppIconButton
          :icon="appIcons.edit"
          tooltip="Rename this pipeline"
          data-testid="pipeline-rename"
          @click="startRename"
        />
        <AppIconButton
          :icon="appIcons.delete"
          tooltip="Delete this pipeline"
          data-testid="pipeline-delete"
          @click="removePipeline"
        />
        <AppButton
          variant="quiet"
          size="sm"
          :icon="appIcons.add"
          label="New"
          :loading="creating"
          data-testid="pipeline-new"
          @click="emit('create')"
        />
      </template>
    </AppCardHead>

    <div
      v-if="pipeline.isPending.value"
      class="pipeline-view__center"
    >
      <AppSpinner />
    </div>
    <AppBanner
      v-else-if="pipeline.isError.value"
      tone="error"
    >
      {{ messageOf(pipeline.error.value, "The pipeline could not be read") }}
    </AppBanner>
    <template v-else>
      <AppBanner
        v-if="pipeline.data.value?.broken"
        tone="warning"
      >
        What was kept of this pipeline could not be read, so it starts empty.
      </AppBanner>
      <div
        ref="canvasBox"
        class="pipeline-view__canvas"
        data-testid="pipeline-canvas"
        @dragover="over"
        @drop="drop"
      >
        <Graph2D
          ref="canvas"
          :graph="graph"
          :positions="positions"
          :camera="camera"
          :expanded="true"
          :selection="selection"
          :dim-others="false"
          @camera="camera = $event"
          @move="move"
          @select="selection = $event"
          @activate="edit"
        >
          <template #node-head="{ node }">
            <AppIconButton
              :icon="appIcons.settings"
              tooltip="Choose what this card holds"
              :data-testid="`pipeline-card-settings-${node.label}`"
              @click="edit(node.id)"
            />
            <AppIconButton
              :icon="appIcons.close"
              tooltip="Take this card off the pipeline"
              :data-testid="`pipeline-card-remove-${node.label}`"
              @click="remove(node.id)"
            />
          </template>
        </Graph2D>
        <div
          v-if="cards.length === 0"
          class="pipeline-view__hint"
        >
          <AppEmptyState
            :icon="appIcons.accountTree"
            text="Drag a connection here from the list on the left, or press one."
          />
        </div>
      </div>
    </template>

    <CardPickerWindow
      v-if="picking"
      :connector-id="picking.connectorId"
      :connection-name="picking.connectionName"
      :rows="picking.rows"
      @done="picked"
      @close="picking = null"
    />

    <WindowDialog
      v-model="renameOpen"
      title="Rename pipeline"
      size="sm"
      sizing="content"
    >
      <AppForm layout="section">
        <AppInput
          v-model="renameDraft"
          label="Name"
          data-testid="pipeline-rename-input"
          @keydown.enter="applyRename"
        />
      </AppForm>
      <template #actions>
        <AppButton
          variant="quiet"
          label="Cancel"
          @click="renameOpen = false"
        />
        <AppButton
          label="Rename"
          :disable="renameDraft.trim() === ''"
          data-testid="pipeline-rename-apply"
          @click="applyRename"
        />
      </template>
    </WindowDialog>
  </div>
</template>

<style scoped>
.pipeline-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.pipeline-view__switcher {
  flex: 0 1 280px;
  min-width: 0;
}
.pipeline-view__center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.pipeline-view__canvas {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
}
/* Over the empty canvas and out of its way: the canvas still pans, and a
   connection is still dropped on it through this. */
.pipeline-view__hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
</style>
