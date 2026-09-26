<script setup lang="ts">
import { useQueries, useQueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"
import { computed, onBeforeUnmount, ref, useTemplateRef, watch } from "vue"

import type { Card, CardRow, CardState, ConnectorPublic, HintLink, Link, LinkEnd, PipelineSummary } from "@/client"
import { startedInThisTab } from "@/features/activity/transfers"
import { useAdapterTypes } from "@/features/connectors/api"
import { isJobEvent, JOBS_TOPIC } from "@/features/services/jobs"
import { messageOf } from "@/shared/api/errors"
import { useNow } from "@/shared/freshness/useNow"
import Graph2D from "@/shared/graph/Graph2D.vue"
import type { Camera2, GraphPort, GraphSelection, Point2 } from "@/shared/graph/model"
import { realtime } from "@/shared/realtime/client"
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
  AppTooltip,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import {
  cardStateKey,
  lackingLinks,
  lastRunKey,
  linkOffersKey,
  pipelineKey,
  readCardState,
  readHint,
  readLinkOffers,
  runPipeline,
  useDeletePipeline,
  useLastRun,
  usePipeline,
  useSavePipeline,
} from "./api"
import type { LinkSide } from "./api"
import CardPickerWindow from "./CardPickerWindow.vue"
import LinkPanel from "./LinkPanel.vue"
import {
  chainOf,
  dependents,
  endOf,
  hintEdges,
  hintOf,
  joinProblem,
  keptLinks,
  linkBetween,
  linkEdge,
  linkFromOffer,
  listed,
  madeRows,
  refusal,
  runProblem,
  runSummary,
  usable,
} from "./links"
import {
  CONNECTION_DRAG,
  dropSpot,
  freeSpot,
  movedCard,
  pipelineGraph,
  positionsOf,
  revealing,
  withoutCard,
  withRows,
  worldPoint,
} from "./model"
import type { CardConnection } from "./model"

/**
 * One pipeline: its head, the canvas of its cards and the links between their
 * rows (D175, D176), and the panel of the link selected.
 *
 * Cards and links are held here as a draft and saved whole a moment after the
 * last change, with the version they were read at, as a dashboard is (D129).
 * The pipeline runs whole by what was saved, so Run saves first (D177).
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
/** The server's bounds on a pipeline (MAX_CARDS, MAX_LINKS), said before one is made. */
const MAX_CARDS = 50
const MAX_LINKS = 200
const HOME: Camera2 = { x: 32, y: 32, zoom: 1 }

const toast = useToast()
const confirm = useConfirm()
const queryClient = useQueryClient()
const pipeline = usePipeline(() => props.pipelineId)
const saving = useSavePipeline()
const deleting = useDeletePipeline()
const adapterTypes = useAdapterTypes()
const lastRun = useLastRun(() => props.pipelineId)
const now = useNow()

const name = ref("")
const version = ref(0)
const cards = ref<Card[]>([])
const links = ref<Link[]>([])
// The cards as the server last confirmed them: what a check is asked about.
const saved = ref<Card[]>([])
const camera = ref<Camera2 | null>(null)
const selection = ref<GraphSelection>(null)
const hints = ref<HintLink[]>([])
const hinting = ref(false)
const starting = ref(false)
const canvasBox = useTemplateRef<HTMLElement>("canvasBox")
const canvas = useTemplateRef<InstanceType<typeof Graph2D>>("canvas")

let timer: ReturnType<typeof setTimeout> | undefined
// A change not yet sent, and the save on its way with whether it kept it.
let pending = false
let sending: Promise<boolean> | null = null

// Read, or read again after a conflict. Not while a change of this screen is
// waiting or on its way: the answer to that save is the newer one.
watch(
  () => pipeline.data.value,
  (read) => {
    if (read === undefined || pending || sending !== null || read.version === version.value) return
    name.value = read.name
    version.value = read.version
    cards.value = [...(read.cards ?? [])]
    links.value = [...(read.links ?? [])]
    saved.value = cards.value
  },
  { immediate: true }
)

function schedule() {
  pending = true
  clearTimeout(timer)
  timer = setTimeout(() => void save(), SAVE_DELAY_MS)
}

async function send(): Promise<boolean> {
  try {
    const answer = await saving.mutateAsync({
      id: props.pipelineId,
      body: { name: name.value, version: version.value, cards: cards.value, links: links.value },
    })
    version.value = answer.version
    saved.value = answer.cards ?? []
    return true
  } catch (cause) {
    if (cause instanceof AxiosError && cause.response?.status === 409) {
      toast.error("This pipeline was changed somewhere else; it has been read again")
      pending = false
      version.value = 0
      await queryClient.invalidateQueries({ queryKey: pipelineKey(props.pipelineId) })
      return false
    }
    toast.error(messageOf(cause, "The pipeline could not be saved"))
    return false
  }
}

/**
 * Send what is waiting, after whatever is on its way; whether all of it was
 * kept. Every caller loops rather than trusting one answer: a change made
 * while a save was travelling is sent by the next turn.
 */
async function save(): Promise<boolean> {
  let kept = true
  while (sending !== null || pending) {
    if (sending !== null) {
      kept = await sending
      continue
    }
    clearTimeout(timer)
    pending = false
    sending = send().finally(() => { sending = null })
    kept = await sending
  }
  return kept
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

// Numbered as the server last answered: a link drawn since gets its number
// when its save comes back.
const order = computed(() => new Map((pipeline.data.value?.order ?? []).map((place) => [place.link_id, place])))
// What each link makes, named by the server as its last save stood (D178).
const results = computed(() => pipeline.data.value?.results ?? [])
const linkRuns = computed(() => new Map((lastRun.data.value?.links ?? []).map((run) => [run.link_id, run])))
const edges = computed(() => [
  ...links.value.map((link) => linkEdge(link, order.value.get(link.id), linkRuns.value.get(link.id))),
  ...hintEdges(hints.value),
])
const graph = computed(() =>
  pipelineGraph(
    cards.value, connectionsById.value, states.value, typeTitles.value, edges.value,
    madeRows(results.value, links.value, order.value)
  )
)
const positions = computed(() => positionsOf(cards.value))
const switcher = computed(() => props.pipelines.map((one) => ({ label: one.name, value: one.id })))

function move(id: string, point: Point2) {
  cards.value = movedCard(cards.value, id, point)
  schedule()
}

/** A card by its id and what it is called now. */
function cardName(card: Card): string {
  return connectionsById.value.get(card.connector_id)?.name ?? card.connector_name
}

/** One end of a link as a sentence names it: "Sales · orders", "Files (top)". */
function nameEnd(end: LinkEnd): string {
  const card = cards.value.find((one) => one.id === end.card_id)
  if (card === undefined) return "a card no longer here"
  if (end.made_by != null) {
    const made = results.value.find((one) => one.link_id === end.made_by)
    return `${cardName(card)} · ${made?.name ?? "what a link makes"}`
  }
  if (end.node_id == null) return `${cardName(card)} (top)`
  const row = card.rows.find((one) => one.node_id === end.node_id)
  return `${cardName(card)} · ${row?.label ?? end.node_id}`
}

function sideOf(end: LinkEnd): LinkSide | null {
  const card = cards.value.find((one) => one.id === end.card_id)
  return card === undefined ? null : { connectorId: card.connector_id, end }
}

/** The links making what either end is, as a key: a choice changed along the chain asks again. */
function chainKey(from: LinkEnd, to: LinkEnd): string {
  return JSON.stringify(
    [...chainOf(links.value, from), ...chainOf(links.value, to)]
      .map((link) => [link.id, link.kind, link.name ?? null, link.columns ?? null, link.source])
  )
}

// Hints answer for the canvas as it was asked; a card or a link changed
// since makes them an answer to another question.
function forgetHints() {
  hints.value = []
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
    connectionName: cardName(card),
    cardId,
    rows: card.rows,
    spot: { x: card.x, y: card.y },
    clear: false,
  }
}

async function picked(rows: CardRow[]) {
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
    const box = canvasBox.value?.getBoundingClientRect()
    if (box !== undefined) camera.value = revealing(camera.value ?? HOME, box, spot, rows.length)
  } else {
    const staying = keptLinks(links.value, made.cardId, rows)
    const going = links.value.filter((link) => !staying.includes(link))
    if (going.length > 0) {
      const sure = await confirm({
        title: "Untick rows that links use?",
        message: `These links go with the rows unticked: ${listed(going, nameEnd)}.`,
        confirmLabel: "Untick",
      })
      if (!sure) return
    }
    cards.value = withRows(cards.value, made.cardId, rows)
    links.value = staying
  }
  forgetHints()
  schedule()
}

async function remove(cardId: string) {
  const card = cards.value.find((one) => one.id === cardId)
  const touching = links.value.filter((link) => link.source.card_id === cardId || link.target.card_id === cardId)
  const going = [...touching, ...dependents(links.value, new Set(touching.map((link) => link.id)))]
  const label = card === undefined ? "The card" : cardName(card)
  const sure = await confirm({
    title: "Take this card off the pipeline?",
    message: going.length === 0
      ? `${label} and what is ticked on it leave this pipeline. Nothing in the connection changes.`
      : `${label} leaves this pipeline, and with it these links: ${listed(going, nameEnd)}. Nothing in the connections changes.`,
    confirmLabel: "Take off",
  })
  if (!sure) return
  cards.value = withoutCard(cards.value, cardId)
  links.value = links.value.filter((link) => !going.includes(link))
  if (selection.value?.id === cardId || going.some((link) => link.id === selection.value?.id)) selection.value = null
  forgetHints()
  schedule()
}

/**
 * Join two rows: the server says what can go from one into the other, and
 * a link is drawn only when something can (D176).
 */
async function join(from: LinkEnd, to: LinkEnd) {
  const problem = joinProblem(cards.value, from, to)
  if (problem !== null) {
    toast.info(problem)
    return
  }
  const already = linkBetween(links.value, from, to)
  if (already !== null) {
    selection.value = { kind: "edge", id: already.id }
    return
  }
  if (links.value.length >= MAX_LINKS) {
    toast.error(`A pipeline holds at most ${String(MAX_LINKS)} links`)
    return
  }
  const source = sideOf(from)
  const target = sideOf(to)
  if (source === null || target === null) return
  let offers
  try {
    // The pipeline as kept answers: a card just placed, or the link making
    // what an end is, has to be there first (D178).
    if (!(await save())) return
    offers = await queryClient.fetchQuery({
      queryKey: linkOffersKey(props.pipelineId, source, target, chainKey(from, to)),
      queryFn: () => readLinkOffers(props.pipelineId, source, target),
      staleTime: 60_000,
    })
  } catch (cause) {
    toast.error(messageOf(cause, "What these rows can do could not be read"))
    return
  }
  const fit = usable(offers)
  const first = fit[0]
  if (first === undefined) {
    toast.info(refusal(offers))
    return
  }
  const link = linkFromOffer(crypto.randomUUID(), from, to, first)
  links.value = [...links.value, link]
  hints.value = hints.value.filter((hint) => linkBetween([link], hint.source, hint.target) === null)
  selection.value = { kind: "edge", id: link.id }
  schedule()
}

function connect(from: GraphPort, to: GraphPort) {
  void join(endOf(from), endOf(to))
}

function select(value: GraphSelection) {
  const hint = value?.kind === "edge" ? hintOf(hints.value, value.id) : null
  if (hint !== null) {
    void join(hint.source, hint.target)
    return
  }
  selection.value = value
}

const selectedLink = computed(() =>
  selection.value?.kind === "edge" ? links.value.find((link) => link.id === selection.value?.id) ?? null : null
)
const panelSides = computed(() => {
  const link = selectedLink.value
  if (link === null) return null
  const from = sideOf(link.source)
  const to = sideOf(link.target)
  return from === null || to === null ? null : { from, to }
})

function changeLink(changed: Link) {
  links.value = links.value.map((link) => (link.id === changed.id ? changed : link))
  schedule()
}

/** Another operation chosen: one that makes nothing takes the links using what this one made. */
async function operate(changed: Link, makes: boolean) {
  const going = makes ? [] : dependents(links.value, new Set([changed.id]))
  if (going.length > 0) {
    const sure = await confirm({
      title: "Change what this link does?",
      message: `${changed.title} makes nothing for later links to read, so these go: ${listed(going, nameEnd)}.`,
      confirmLabel: "Change",
    })
    if (!sure) return
    links.value = links.value.filter((link) => !going.includes(link))
  }
  changeLink(changed)
}

async function removeLink(link: Link) {
  const going = dependents(links.value, new Set([link.id]))
  const sure = await confirm({
    title: "Remove this link?",
    message: going.length === 0
      ? `${nameEnd(link.source)} → ${nameEnd(link.target)} and the choices kept with it go. Nothing in the connections changes.`
      : `${nameEnd(link.source)} → ${nameEnd(link.target)} goes, and with what it makes these links: ${listed(going, nameEnd)}. Nothing in the connections changes.`,
    confirmLabel: "Remove",
  })
  if (!sure) return
  links.value = links.value.filter((one) => one.id !== link.id && !going.includes(one))
  selection.value = null
  schedule()
}

const runBlocked = computed(() => runProblem(links.value, lastRun.data.value))
const lastRunFailed = computed(() => ["failed", "interrupted"].includes(lastRun.data.value?.state ?? ""))

/** Every link, in order, as one job; the footer follows it from here. */
async function run() {
  if (starting.value || runBlocked.value !== null) return
  starting.value = true
  try {
    // What runs is what is kept, so what is on the screen is kept first.
    if (!(await save())) return
    const answer = await runPipeline(props.pipelineId)
    queryClient.setQueryData(lastRunKey(props.pipelineId), answer)
    startedInThisTab(answer.job_id)
  } catch (cause) {
    // A link lacking a choice is opened, so the choice is one press away.
    const first = lackingLinks(cause)[0]
    if (first !== undefined) selection.value = { kind: "edge", id: first }
    toast.error(messageOf(cause, "The pipeline could not run"))
  } finally {
    starting.value = false
  }
}

// Every step of a run moves its job; the last run is read again each time,
// so the lines take their colours as the steps end.
const stopListening = realtime().subscribe(JOBS_TOPIC, (payload) => {
  if (!isJobEvent(payload) || payload.kind !== "pipeline.run" || payload.subject_id !== props.pipelineId) return
  void queryClient.invalidateQueries({ queryKey: lastRunKey(props.pipelineId) })
})
onBeforeUnmount(stopListening)

/** Every link that could be drawn, dashed; pressed again, they go. */
async function toggleHint() {
  if (hints.value.length > 0) {
    forgetHints()
    return
  }
  hinting.value = true
  try {
    if (!(await save())) return
    const card = selection.value?.kind === "node" ? selection.value.id : null
    const answer = await readHint(props.pipelineId, card)
    hints.value = answer.links
    if (answer.notice) toast.info(answer.notice)
    else if (answer.links.length === 0) toast.info("No other link can be drawn between these rows")
  } catch (cause) {
    toast.error(messageOf(cause, "The possible links could not be read"))
  } finally {
    hinting.value = false
  }
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
      <span
        v-if="lastRun.data.value"
        class="pipeline-view__last-run"
        :class="{ 'pipeline-view__last-run--failed': lastRunFailed }"
        data-testid="pipeline-last-run"
      >{{ runSummary(lastRun.data.value, now) }}<AppTooltip>{{ runSummary(lastRun.data.value, now) }}</AppTooltip></span>
      <template #actions>
        <span class="pipeline-view__run">
          <AppButton
            size="sm"
            :icon="appIcons.playArrow"
            label="Run"
            :disable="runBlocked !== null"
            :loading="starting"
            data-testid="pipeline-run"
            @click="run"
          />
          <AppTooltip>{{ runBlocked ?? "Run every link, one after another, as saved" }}</AppTooltip>
        </span>
        <AppIconButton
          :icon="appIcons.lightbulb"
          :tooltip="hints.length > 0 ? 'Hide the possible links' : 'Show the links that could be drawn'"
          :active="hints.length > 0"
          :loading="hinting"
          data-testid="pipeline-hint"
          @click="toggleHint"
        />
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
          linkable
          edge-labels
          @camera="camera = $event"
          @move="move"
          @select="select"
          @activate="edit"
          @connect="connect"
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
      <LinkPanel
        v-if="selectedLink && panelSides"
        :key="selectedLink.id"
        :link="selectedLink"
        :from="panelSides.from"
        :to="panelSides.to"
        :name="nameEnd"
        :pipeline-id="pipelineId"
        :chain="chainKey(selectedLink.source, selectedLink.target)"
        :prepare="save"
        :place="order.get(selectedLink.id)"
        :link-run="linkRuns.get(selectedLink.id)"
        :last-run="lastRun.data.value"
        @change="changeLink"
        @operate="operate"
        @remove="removeLink(selectedLink)"
        @close="selection = null"
      />
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
.pipeline-view__last-run {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--dp-text-muted);
  font-size: 12px;
}
.pipeline-view__last-run--failed {
  color: var(--dp-tone-warning-text);
}
.pipeline-view__run {
  display: inline-flex;
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
