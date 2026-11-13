<script setup lang="ts">
import { useQueries, useQueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"
import { computed, onBeforeUnmount, ref, useTemplateRef, watch } from "vue"

import type { Card, CardRow, CardState, ConnectorPublic, Link, LinkEnd, PipelineSummary } from "@/client"
import { startedInThisTab } from "@/features/activity/transfers"
import { useAdapterTypes } from "@/features/connectors/api"
import { isJobEvent, JOBS_TOPIC } from "@/features/services/jobs"
import { messageOf } from "@/shared/api/errors"
import { useNow } from "@/shared/freshness/useNow"
import { t } from "@/shared/i18n"
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
  AppMenu,
  AppSelect,
  AppSpinner,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import {
  cardStateKey,
  historyKey,
  lackingLinks,
  lastRunKey,
  linkOffersKey,
  problemCode,
  scheduleKey,
  setSwitch,
  switchKey,
  useSwitch,
  pipelineKey,
  readCardState,
  readLinkOffers,
  readTargets,
  runPipeline,
  useDeletePipeline,
  useLastRun,
  usePastRun,
  usePipeline,
  useSavePipeline,
  useSchedule,
} from "./api"
import type { LinkSide } from "./api"
import CardPickerWindow from "./CardPickerWindow.vue"
import { shownWords } from "./history"
import HistoryWindow from "./HistoryWindow.vue"
import LinkPanel from "./LinkPanel.vue"
import { followedLinks, followTone } from "./follow"
import ScheduleWindow from "./ScheduleWindow.vue"
import { statusLine } from "./status"
import {
  chainOf,
  dependents,
  endOf,
  joinProblem,
  keptLinks,
  linkBetween,
  linkEdge,
  linkFromOffer,
  listed,
  madeRows,
  needsDialog,
  refusal,
  runProblem,
  targetRows,
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
  rowKey,
  withoutCard,
  withRows,
  worldPoint,
} from "./model"
import type { CardConnection, RowTarget } from "./model"
import { newId } from "@/shared/ids"

/**
 * One pipeline: its head, the canvas of its cards and the links between their
 * rows (D175, D176), and the panel of the link selected.
 *
 * Cards and links are held here as a draft and saved whole a moment after the
 * last change, with the version they were read at, as a dashboard is (D129).
 * What runs is what was saved, so Switch on and Run once save first (D177,
 * D362). The lines say what the last run did, or an older one pressed in the
 * history (D180); the status line at the foot says what the pipeline needs or
 * does now (D364).
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
const timetable = useSchedule(() => props.pipelineId)
const scheduling = ref(false)
// Whether the pipeline is on, its status line, and what each continuous link did (D362, D364).
const switchState = useSwitch(() => props.pipelineId)
const switchOn = computed(() => switchState.data.value?.on === true)
const followed = computed(() => followedLinks(switchState.data.value))
const switching = ref(false)
const now = useNow()
const status = computed(() => statusLine(switchState.data.value?.status, now.value))

/** Switched on — what is on the screen kept first, since what runs is what is kept — or off. */
async function toggleSwitch() {
  if (switching.value) return
  switching.value = true
  const on = !switchOn.value
  try {
    if (on && !(await save())) return
    const answer = await setSwitch(props.pipelineId, on)
    queryClient.setQueryData(switchKey(props.pipelineId), answer)
    if (answer.follow?.running === true && answer.follow.job_id) startedInThisTab(answer.follow.job_id)
    void queryClient.invalidateQueries({ queryKey: scheduleKey(props.pipelineId) })
  } catch (cause) {
    // What it lacks is opened, so it is one press away.
    if (problemCode(cause) === "pipelines.no_schedule") scheduling.value = true
    openLacking(cause)
    toast.error(messageOf(cause, t("pipelines.switch.failed")))
  } finally {
    switching.value = false
  }
}

/** The first link a refusal named as lacking a choice, selected with its window open. */
function openLacking(cause: unknown) {
  const first = lackingLinks(cause)[0]
  if (first === undefined) return
  selection.value = { kind: "edge", id: first }
  autoOpenLinkId.value = first
}

const runMenu = computed(() => [
  {
    name: "schedule",
    label: t("pipelines.view.schedule"),
    icon: appIcons.schedule,
  },
  {
    name: "run-once",
    label: t("pipelines.view.run_once"),
    icon: appIcons.playArrow,
    disable: runBlocked.value !== null || starting.value,
    hint: runBlocked.value ?? undefined,
  },
])
const moreMenu = computed(() => [
  { name: "history", label: t("pipelines.view.history"), icon: appIcons.history },
  { name: "rename", label: t("pipelines.view.rename_tooltip"), icon: appIcons.edit },
  { name: "delete", label: t("pipelines.view.delete_tooltip"), icon: appIcons.delete, danger: true },
])

function pickRun(name: string) {
  if (name === "schedule") scheduling.value = true
  else if (name === "run-once") void run()
}

function pickMore(name: string) {
  if (name === "history") historyOpen.value = true
  else if (name === "rename") startRename()
  else if (name === "delete") void removePipeline()
}

/** The status line's action: the link it names, the schedule, or the history. */
function statusAction() {
  const line = status.value
  if (line === null) return
  if (line.action === "schedule") scheduling.value = true
  else if (line.action === "history") historyOpen.value = true
  else if (line.action === "link" && line.linkId !== null) {
    selection.value = { kind: "edge", id: line.linkId }
    autoOpenLinkId.value = line.linkId
  }
}
const historyOpen = ref(false)
// An older run pressed in the history, or none while the last is shown.
const pastJobId = ref<string | null>(null)
const pastRun = usePastRun(() => props.pipelineId, pastJobId)
const shownRun = computed(() => (pastJobId.value === null ? lastRun.data.value : pastRun.data.value))

function showRun(jobId: string) {
  pastJobId.value = jobId === lastRun.data.value?.job_id ? null : jobId
}

watch(() => props.pipelineId, () => { pastJobId.value = null })
// Gone from the history since it was pressed, say: the last run comes back.
watch(
  () => pastRun.isError.value,
  (failed) => {
    if (!failed || pastJobId.value === null) return
    toast.info(t("pipelines.view.past_run_failed"))
    pastJobId.value = null
  }
)

const name = ref("")
const version = ref(0)
const cards = ref<Card[]>([])
const links = ref<Link[]>([])
// The cards as the server last confirmed them: what a check is asked about.
const saved = ref<Card[]>([])
const camera = ref<Camera2 | null>(null)
const selection = ref<GraphSelection>(null)
// A link that still needs its table or column choices — just drawn, given
// another operation, or named by a Run that failed on it — opens its window.
const autoOpenLinkId = ref<string | null>(null)
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
    // What a link lacks, and so the status line, follows what was kept (D364).
    void queryClient.invalidateQueries({ queryKey: switchKey(props.pipelineId) })
    return true
  } catch (cause) {
    if (cause instanceof AxiosError && cause.response?.status === 409) {
      toast.error(t("pipelines.view.changed_elsewhere"))
      pending = false
      version.value = 0
      await queryClient.invalidateQueries({ queryKey: pipelineKey(props.pipelineId) })
      return false
    }
    toast.error(messageOf(cause, t("pipelines.view.save_failed")))
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
const readers = computed(() => new Map((pipeline.data.value?.readers ?? []).map((one) => [one.link_id, one.name])))
const linkRuns = computed(() => new Map((shownRun.value?.links ?? []).map((run) => [run.link_id, run])))
// What each link still needs, as the server last answered a save (D364).
const lacks = computed(() => new Map((pipeline.data.value?.lacking ?? []).map((one) => [one.link_id, one])))
const edges = computed(() =>
  links.value.map((link) =>
    linkEdge(
      link,
      order.value.get(link.id),
      linkRuns.value.get(link.id),
      switchOn.value && link.runs === "continuous" ? followTone(followed.value.get(link.id)) ?? null : undefined,
      lacks.value.get(link.id)
    )
  )
)

// While a row is dragged (D363): what a drop on each row would do, or why not.
const dragFrom = ref<LinkEnd | null>(null)
const targets = ref<Map<string, RowTarget> | null>(null)
const partial = ref(false)
const askedCards = new Set<string>()
let dragTurn = 0

function merge(found: Map<string, RowTarget>) {
  targets.value = new Map([...(targets.value ?? []), ...found])
}

async function linking(from: GraphPort | null) {
  dragTurn += 1
  const turn = dragTurn
  askedCards.clear()
  partial.value = false
  targets.value = null
  dragFrom.value = null
  if (from === null) return
  const end = endOf(from)
  // The top of a connection takes things; it is refused at the drop.
  if (end.node_id == null && end.made_by == null) return
  dragFrom.value = end
  try {
    // The pipeline as kept answers, as it does a drop.
    if (!(await save()) || turn !== dragTurn) return
    const answer = await readTargets(props.pipelineId, end, null)
    if (turn !== dragTurn) return
    partial.value = answer.partial === true
    merge(targetRows(answer.targets ?? []))
  } catch {
    // Nothing tinted: the drop is asked as it always was.
  }
}

/** A canvas too large to answer whole: a card's rows are asked when the pointer reaches it. */
async function aim(port: GraphPort | null) {
  const from = dragFrom.value
  if (port === null || from === null || !partial.value || askedCards.has(port.nodeId)) return
  askedCards.add(port.nodeId)
  const turn = dragTurn
  try {
    const answer = await readTargets(props.pipelineId, from, port.nodeId)
    if (turn === dragTurn) merge(targetRows(answer.targets ?? []))
  } catch {
    // That card stays untinted.
  }
}

const graph = computed(() =>
  pipelineGraph(
    cards.value, connectionsById.value, states.value, typeTitles.value, edges.value,
    madeRows(results.value, links.value, order.value), targets.value
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

/**
 * What one end is called on its own: a row's label, or what a link makes.
 * Nothing for the top of a card, which is named by its connection alone.
 */
function labelEnd(end: LinkEnd): string | null {
  const card = cards.value.find((one) => one.id === end.card_id)
  if (card === undefined) return null
  if (end.made_by != null) {
    const made = results.value.find((one) => one.link_id === end.made_by)
    return made?.name ?? t("pipelines.view.made_by_link")
  }
  if (end.node_id == null) return null
  return card.rows.find((one) => one.node_id === end.node_id)?.label ?? end.node_id
}

/** One end of a link as a sentence names it: "Sales · orders", "Files (top)". */
function nameEnd(end: LinkEnd): string {
  const card = cards.value.find((one) => one.id === end.card_id)
  if (card === undefined) return t("pipelines.view.card_gone")
  const label = labelEnd(end)
  return label === null
    ? t("pipelines.view.end_top", { card: cardName(card) })
    : t("pipelines.view.end", { card: cardName(card), label })
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
    toast.error(t("pipelines.view.switched_off", { name: connection.name }))
    return
  }
  if (cards.value.length >= MAX_CARDS) {
    toast.error(t("pipelines.view.max_cards", { n: MAX_CARDS }))
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
      id: newId(),
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
        title: t("pipelines.view.untick_title"),
        message: t("pipelines.view.untick_message", { links: listed(going, nameEnd) }),
        confirmLabel: t("pipelines.view.untick"),
      })
      if (!sure) return
    }
    cards.value = withRows(cards.value, made.cardId, rows)
    links.value = staying
  }
  schedule()
}

async function remove(cardId: string) {
  const card = cards.value.find((one) => one.id === cardId)
  const touching = links.value.filter((link) => link.source.card_id === cardId || link.target.card_id === cardId)
  const going = [...touching, ...dependents(links.value, new Set(touching.map((link) => link.id)))]
  const label = card === undefined ? t("pipelines.view.the_card") : cardName(card)
  const sure = await confirm({
    title: t("pipelines.view.take_off_title"),
    message: going.length === 0
      ? t("pipelines.view.take_off_alone", { card: label })
      : t("pipelines.view.take_off_links", { card: label, links: listed(going, nameEnd) }),
    confirmLabel: t("pipelines.view.take_off"),
  })
  if (!sure) return
  cards.value = withoutCard(cards.value, cardId)
  links.value = links.value.filter((link) => !going.includes(link))
  if (selection.value?.id === cardId || going.some((link) => link.id === selection.value?.id)) selection.value = null
  if (autoOpenLinkId.value !== null && going.some((link) => link.id === autoOpenLinkId.value)) autoOpenLinkId.value = null
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
    toast.error(t("pipelines.view.max_links", { n: MAX_LINKS }))
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
    toast.error(messageOf(cause, t("pipelines.view.offers_failed")))
    return
  }
  const fit = usable(offers)
  const first = fit[0]
  if (first === undefined) {
    toast.info(refusal(offers))
    return
  }
  // Drawn with what the server says it starts with: ready, unless a choice
  // cannot be guessed, and then its window opens (D364).
  const link = linkFromOffer(newId(), from, to, first)
  links.value = [...links.value, link]
  selection.value = { kind: "edge", id: link.id }
  autoOpenLinkId.value = needsDialog(link, first.workflow ?? "run") ? link.id : null
  schedule()
}

function connect(from: GraphPort, to: GraphPort) {
  // A row the drag already answered for cannot take it: nothing is drawn, and its reason was in view.
  const known = targets.value?.get(rowKey(to.nodeId, to.portId))
  if (known !== undefined && !known.fit) return
  void join(endOf(from), endOf(to))
}

function select(value: GraphSelection) {
  if (value?.kind !== "edge" || value.id !== autoOpenLinkId.value) autoOpenLinkId.value = null
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

function closePanel() {
  selection.value = null
  autoOpenLinkId.value = null
}

/** Another operation chosen: one that makes nothing takes the links using what this one made. */
async function operate(changed: Link, makes: boolean) {
  const going = makes ? [] : dependents(links.value, new Set([changed.id]))
  if (going.length > 0) {
    const sure = await confirm({
      title: t("pipelines.view.change_title"),
      message: t("pipelines.view.change_message", { operation: changed.title, links: listed(going, nameEnd) }),
      confirmLabel: t("pipelines.view.change"),
    })
    if (!sure) return
    links.value = links.value.filter((link) => !going.includes(link))
  }
  changeLink(changed)
  autoOpenLinkId.value = changed.id
}

async function removeLink(link: Link) {
  const going = dependents(links.value, new Set([link.id]))
  const sure = await confirm({
    title: t("pipelines.view.remove_link_title"),
    message: going.length === 0
      ? t("pipelines.view.remove_link_alone", { from: nameEnd(link.source), to: nameEnd(link.target) })
      : t("pipelines.view.remove_link_more", {
        from: nameEnd(link.source), to: nameEnd(link.target), links: listed(going, nameEnd),
      }),
    confirmLabel: t("pipelines.view.remove"),
  })
  if (!sure) return
  links.value = links.value.filter((one) => one.id !== link.id && !going.includes(one))
  selection.value = null
  if (autoOpenLinkId.value === link.id) autoOpenLinkId.value = null
  schedule()
}

const runBlocked = computed(() => runProblem(links.value, lastRun.data.value))

/** Every link, in order, as one job; the lines and the footer follow it from here. */
async function run() {
  if (starting.value || runBlocked.value !== null) return
  starting.value = true
  try {
    // What runs is what is kept, so what is on the screen is kept first.
    if (!(await save())) return
    const answer = await runPipeline(props.pipelineId)
    queryClient.setQueryData(lastRunKey(props.pipelineId), answer)
    pastJobId.value = null
    startedInThisTab(answer.job_id)
  } catch (cause) {
    // A link lacking a choice is opened, so the choice is one press away.
    openLacking(cause)
    toast.error(messageOf(cause, t("pipelines.view.run_failed")))
  } finally {
    starting.value = false
  }
}

// Every step of a run moves its job; the last run is read again each time,
// so the lines take their colours as the steps end.
const stopListening = realtime().subscribe(JOBS_TOPIC, (payload) => {
  if (!isJobEvent(payload) || payload.kind !== "pipeline.run" || payload.subject_id !== props.pipelineId) return
  void queryClient.invalidateQueries({ queryKey: lastRunKey(props.pipelineId) })
  void queryClient.invalidateQueries({ queryKey: historyKey(props.pipelineId) })
  // A run the schedule started moves its next time on (D179).
  if (payload.state === "queued" || payload.state === "running") {
    void queryClient.invalidateQueries({ queryKey: switchKey(props.pipelineId) })
  }
})
onBeforeUnmount(stopListening)

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
    title: t("pipelines.view.delete_title"),
    message: t("pipelines.view.delete_message", { name: name.value, n: cards.value.length }, cards.value.length),
    confirmLabel: t("pipelines.view.delete"),
    danger: true,
  })
  if (!sure) return
  pending = false
  clearTimeout(timer)
  try {
    await deleting.mutateAsync(props.pipelineId)
    emit("deleted")
  } catch (cause) {
    toast.error(messageOf(cause, t("pipelines.view.delete_failed")))
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
        :aria-label="t('pipelines.view.pipeline')"
        data-testid="pipeline-switcher"
        @update:model-value="emit('select', String($event))"
      />
      <template #actions>
        <span class="pipeline-view__switch">
          <AppButton
            size="sm"
            :variant="switchOn ? 'secondary' : 'primary'"
            :icon="switchOn ? appIcons.stop : appIcons.playArrow"
            :label="switchOn ? t('pipelines.view.switch_off') : t('pipelines.view.switch_on')"
            :loading="switching"
            data-testid="pipeline-switch"
            @click="toggleSwitch"
          />
          <span>
            <AppIconButton
              :icon="appIcons.expandMore"
              :tooltip="t('pipelines.view.run_menu')"
              :loading="starting"
              data-testid="pipeline-run-menu"
            />
            <AppMenu
              :items="runMenu"
              @select="pickRun"
            />
          </span>
        </span>
        <AppIconButton
          :icon="appIcons.centerFocusStrong"
          :tooltip="t('pipelines.view.fit')"
          data-testid="pipeline-fit"
          @click="canvas?.fit()"
        />
        <span>
          <AppIconButton
            :icon="appIcons.moreVert"
            :tooltip="t('pipelines.view.more')"
            data-testid="pipeline-more"
          />
          <AppMenu
            :items="moreMenu"
            @select="pickMore"
          />
        </span>
        <AppButton
          variant="quiet"
          size="sm"
          :icon="appIcons.add"
          :label="t('pipelines.view.new')"
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
      {{ messageOf(pipeline.error.value, t('pipelines.view.read_failed')) }}
    </AppBanner>
    <template v-else>
      <AppBanner
        v-if="pipeline.data.value?.broken"
        tone="warning"
      >
        {{ t('pipelines.view.broken') }}
      </AppBanner>
      <AppBanner
        v-if="pastJobId !== null && pastRun.data.value"
        tone="info"
        data-testid="pipeline-shown-run"
      >
        {{ shownWords(pastRun.data.value, now) }}
        <template #action>
          <AppButton
            variant="quiet"
            size="sm"
            :label="t('pipelines.view.back_to_last')"
            data-testid="pipeline-shown-run-back"
            @click="pastJobId = null"
          />
        </template>
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
          @linking="linking"
          @aim="aim"
        >
          <template #node-head="{ node }">
            <AppIconButton
              :icon="appIcons.settings"
              :tooltip="t('pipelines.view.card_settings')"
              :data-testid="`pipeline-card-settings-${node.label}`"
              compact
              @click="edit(node.id)"
            />
            <AppIconButton
              :icon="appIcons.close"
              :tooltip="t('pipelines.view.card_remove')"
              :data-testid="`pipeline-card-remove-${node.label}`"
              compact
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
            :text="t('pipelines.view.empty')"
          />
        </div>
      </div>
      <div
        v-if="status && cards.length > 0"
        class="pipeline-view__status"
        :class="`pipeline-view__status--${status.tone}`"
        role="status"
        data-testid="pipeline-status"
        :data-kind="switchState.data.value?.status.kind"
      >
        <q-icon
          :name="status.tone === 'caution' ? appIcons.warningAmber : status.tone === 'working' ? appIcons.sensors : appIcons.info"
          size="var(--dp-icon-sm)"
        />
        <span class="pipeline-view__status-text">{{ status.text }}</span>
        <AppButton
          v-if="status.action"
          variant="quiet"
          size="sm"
          :label="status.actionLabel"
          data-testid="pipeline-status-action"
          @click="statusAction"
        />
      </div>
      <LinkPanel
        v-if="selectedLink && panelSides"
        :key="selectedLink.id"
        :link="selectedLink"
        :from="panelSides.from"
        :to="panelSides.to"
        :name="nameEnd"
        :label="labelEnd"
        :pipeline-id="pipelineId"
        :chain="chainKey(selectedLink.source, selectedLink.target)"
        :prepare="save"
        :place="order.get(selectedLink.id)"
        :link-run="linkRuns.get(selectedLink.id)"
        :run="shownRun"
        :past="pastJobId !== null"
        :auto-open="autoOpenLinkId === selectedLink.id"
        :reader="readers.get(selectedLink.id) ?? null"
        :switch-on="switchOn"
        :followed="followed.get(selectedLink.id)"
        @change="changeLink"
        @operate="operate"
        @remove="removeLink(selectedLink)"
        @close="closePanel"
        @auto-opened="autoOpenLinkId = null"
      />
    </template>

    <HistoryWindow
      v-if="historyOpen"
      :pipeline-id="pipelineId"
      :pipeline-name="name"
      :shown-job-id="pastJobId ?? lastRun.data.value?.job_id ?? null"
      @show="showRun"
      @close="historyOpen = false"
    />

    <ScheduleWindow
      v-if="scheduling && !timetable.isPending.value"
      :pipeline-id="pipelineId"
      :pipeline-name="name"
      :settings="timetable.data.value?.settings"
      @close="scheduling = false"
    />

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
      :title="t('pipelines.view.rename_title')"
      size="sm"
      sizing="content"
    >
      <AppForm layout="section">
        <!-- Trap: closed on keydown, the window hands focus back to the
             pencil that opened it, and the same Enter presses that and
             opens it again. Prevented, the Enter ends here. -->
        <AppInput
          v-model="renameDraft"
          :label="t('pipelines.view.name')"
          data-testid="pipeline-rename-input"
          @keydown.enter.prevent="applyRename"
        />
      </AppForm>
      <template #actions>
        <AppButton
          variant="quiet"
          :label="t('catalog.common.cancel')"
          @click="renameOpen = false"
        />
        <AppButton
          :label="t('pipelines.view.rename')"
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
.pipeline-view__switch {
  display: inline-flex;
  align-items: center;
}
/* One line at the foot of the canvas (D364): what the pipeline needs or does now. */
.pipeline-view__status {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-1) var(--dp-space-3);
  border-top: 1px solid var(--dp-border-faint);
  background: var(--dp-chrome);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
.pipeline-view__status--caution {
  background: var(--dp-tone-warning-wash);
  color: var(--dp-tone-warning-text);
}
.pipeline-view__status--working {
  color: var(--dp-content-success);
}
.pipeline-view__status-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  /* Trap: the graph keeps its own height when the panel below squeezes this
     box, and spills over the status line, covering it. */
  overflow: hidden;
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
