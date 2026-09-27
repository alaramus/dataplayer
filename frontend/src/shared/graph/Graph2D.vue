<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, useId } from "vue"

import { AppTooltip } from "@/shared/ui"

import { CARD_WIDTH, HEADER_HEIGHT, ROW_HEIGHT, edgePaths, fit2, labelSpots, portAnchors, zoomAt } from "./layout"
import { accentIndex, edgesOf, neighborsOf } from "./model"
import type { Camera2, GraphDocument, GraphEdge, GraphPort, GraphSelection, Point2 } from "./model"

const props = withDefaults(defineProps<{
  graph: GraphDocument
  positions: Record<string, Point2>
  camera: Camera2 | null
  expanded: boolean
  selection: GraphSelection
  /**
   * Whether a selection fades what it is not connected to. A diagram read
   * for one table's references wants it; a canvas being built does not, where
   * the card just placed would fade every other.
   */
  dimOthers?: boolean
  /** Whether a row is dragged onto a row of another card to join the two. */
  linkable?: boolean
  /** Whether each edge has its label written along it. */
  edgeLabels?: boolean
}>(), { dimOthers: true, linkable: false, edgeLabels: false })
const emit = defineEmits<{
  camera: [value: Camera2]
  move: [id: string, position: Point2]
  select: [value: GraphSelection]
  activate: [id: string]
  connect: [from: GraphPort, to: GraphPort]
}>()
const root = ref<HTMLDivElement>()
const camera = computed(() => props.camera ?? { x: 32, y: 32, zoom: 1 })
const paths = computed(() => edgePaths(props.graph, props.positions, props.expanded))
const anchors = computed(() => portAnchors(paths.value))
const NO_ANCHOR = { left: false, right: false }
const anchorOf = (nodeId: string, portId: string) =>
  anchors.value.get(nodeId)?.get(portId) ?? NO_ANCHOR
const neighbors = computed(() => neighborsOf(props.graph, props.selection))
const highlighted = computed(() => new Set(edgesOf(props.graph, props.selection).map((edge) => edge.id)))
const labelled = computed(() => paths.value.filter((item) => item.edge.label !== "" || item.edge.badge))
const labelText = (edge: GraphEdge) => [edge.badge, edge.label].filter(Boolean).join(" · ")
const spots = computed(() =>
  labelSpots(labelled.value.map((item) => ({ id: item.edge.id, text: labelText(item.edge), curve: item.curve })))
)
const arrowId = `graph-arrow-${useId()}`
const ARROW_TONES = ["plain", "active", "info", "success", "error", "muted"] as const
/** The arrowhead a line ends in: its result's colour, else the selection's. */
function arrowTone(edge: GraphEdge, active: boolean): (typeof ARROW_TONES)[number] {
  return edge.tone ?? (active ? "active" : "plain")
}
const dragging = ref(false)
let resize: ResizeObserver | undefined
let gesture: { pointer: number; capture: HTMLElement; start: Point2; camera: Camera2; node?: { id: string; position: Point2 }; moved: boolean } | null = null
// A row being dragged towards another: where it started, and where the
// pointer is once it has moved far enough to be a drag rather than a press.
const linking = ref<{ pointer: number; capture: HTMLElement; from: GraphPort; start: Point2; at: Point2 | null } | null>(null)
const aimed = ref<GraphPort | null>(null)
// The press that ends a drag is also a click on the row it started from.
let swallowClick = false
const draft = computed(() => {
  const drawn = linking.value
  if (drawn === null || drawn.at === null) return null
  const node = props.graph.nodes.find((one) => one.id === drawn.from.nodeId)
  const point = props.positions[drawn.from.nodeId]
  if (!node || !point) return null
  const index = Math.max(0, node.rows.findIndex((row) => row.id === drawn.from.portId))
  const a = { x: point.x + CARD_WIDTH, y: point.y + HEADER_HEIGHT + (index + 0.5) * ROW_HEIGHT }
  const b = drawn.at
  return `M ${a.x} ${a.y} C ${a.x + 60} ${a.y}, ${b.x - 60} ${b.y}, ${b.x} ${b.y}`
})

function dimensions() {
  return { width: root.value?.clientWidth ?? 0, height: root.value?.clientHeight ?? 0 }
}
function fit() {
  const size = dimensions()
  if (size.width > 0 && size.height > 0) emit("camera", fit2(props.graph, props.positions, props.expanded, size.width, size.height))
}
function zoom(factor: number) {
  const size = dimensions()
  emit("camera", zoomAt(camera.value, factor, { x: size.width / 2, y: size.height / 2 }))
}
function focus(id: string) {
  const point = props.positions[id]
  if (!point) return
  const size = dimensions()
  const scale = Math.max(0.6, camera.value.zoom)
  emit("camera", { zoom: scale, x: size.width / 2 - (point.x + CARD_WIDTH / 2) * scale, y: size.height / 2 - (point.y + HEADER_HEIGHT / 2) * scale })
}
function worldOf(event: PointerEvent): Point2 {
  const bounds = root.value!.getBoundingClientRect()
  return { x: (event.clientX - bounds.left - camera.value.x) / camera.value.zoom, y: (event.clientY - bounds.top - camera.value.y) / camera.value.zoom }
}
/** The row under the pointer, read off the page: a captured pointer hovers nothing else. */
function portAt(event: PointerEvent): GraphPort | null {
  const found = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>("[data-port-id]")
  const nodeId = found?.dataset.portNode
  const portId = found?.dataset.portId
  return nodeId === undefined || portId === undefined ? null : { nodeId, portId }
}
function startLink(event: PointerEvent, nodeId: string, portId: string) {
  if (!props.linkable || event.button !== 0 || !event.isPrimary) return
  const capture = event.currentTarget as HTMLElement
  linking.value = { pointer: event.pointerId, capture, from: { nodeId, portId }, start: { x: event.clientX, y: event.clientY }, at: null }
  capture.setPointerCapture(event.pointerId)
}
function pressRow(nodeId: string, portId: string) {
  if (swallowClick) return
  emit("select", { kind: "node", id: nodeId, portId })
}
function wheel(event: WheelEvent) {
  const bounds = root.value!.getBoundingClientRect()
  emit("camera", zoomAt(camera.value, Math.exp(-Math.max(-150, Math.min(150, event.deltaY)) * 0.006), { x: event.clientX - bounds.left, y: event.clientY - bounds.top }))
}
function start(event: PointerEvent, nodeId?: string) {
  if (event.button !== 0 || !event.isPrimary) return
  if (!nodeId && event.target instanceof Element && event.target.closest("[data-graph-interactive]")) return
  event.preventDefault()
  gesture = {
    pointer: event.pointerId, capture: event.currentTarget as HTMLElement,
    start: { x: event.clientX, y: event.clientY }, camera: { ...camera.value }, moved: false,
    node: nodeId ? { id: nodeId, position: { ...props.positions[nodeId]! } } : undefined,
  }
  // Capture on the header when dragging a card so its double-click still
  // reaches the header instead of being retargeted to the canvas.
  gesture.capture.setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) {
  const drawn = linking.value
  if (drawn && drawn.pointer === event.pointerId) {
    if (drawn.at === null && Math.hypot(event.clientX - drawn.start.x, event.clientY - drawn.start.y) < 3) return
    linking.value = { ...drawn, at: worldOf(event) }
    const port = portAt(event)
    aimed.value = port !== null && port.nodeId !== drawn.from.nodeId ? port : null
    return
  }
  if (!gesture || gesture.pointer !== event.pointerId) return
  const dx = event.clientX - gesture.start.x
  const dy = event.clientY - gesture.start.y
  if (!gesture.moved && Math.hypot(dx, dy) < 3) return
  gesture.moved = true
  dragging.value = true
  if (gesture.node) {
    emit("move", gesture.node.id, { x: gesture.node.position.x + dx / gesture.camera.zoom, y: gesture.node.position.y + dy / gesture.camera.zoom })
  } else {
    emit("camera", { ...gesture.camera, x: gesture.camera.x + dx, y: gesture.camera.y + dy })
  }
}
function end(event: PointerEvent) {
  const drawn = linking.value
  if (drawn && drawn.pointer === event.pointerId) {
    linking.value = null
    aimed.value = null
    if (drawn.capture.hasPointerCapture(event.pointerId)) drawn.capture.releasePointerCapture(event.pointerId)
    if (drawn.at === null) return
    swallowClick = true
    setTimeout(() => { swallowClick = false }, 0)
    const port = portAt(event)
    if (port !== null && port.nodeId !== drawn.from.nodeId) emit("connect", drawn.from, port)
    return
  }
  if (!gesture || gesture.pointer !== event.pointerId) return
  const ended = gesture
  gesture = null
  dragging.value = false
  if (ended.capture.hasPointerCapture(event.pointerId)) ended.capture.releasePointerCapture(event.pointerId)
  if (!ended.moved) emit("select", ended.node ? { kind: "node", id: ended.node.id } : null)
}
function cancel() {
  const drawn = linking.value
  linking.value = null
  aimed.value = null
  if (drawn?.capture.hasPointerCapture(drawn.pointer)) drawn.capture.releasePointerCapture(drawn.pointer)
  const ended = gesture
  gesture = null
  dragging.value = false
  if (!ended) return
  if (ended.node) emit("move", ended.node.id, ended.node.position)
  else emit("camera", ended.camera)
  if (ended.capture.hasPointerCapture(ended.pointer)) ended.capture.releasePointerCapture(ended.pointer)
}
function activated() { if (!props.camera) fit() }
onMounted(() => {
  resize = new ResizeObserver(activated)
  if (root.value) resize.observe(root.value)
  activated()
})
onActivated(activated)
onDeactivated(cancel)
onBeforeUnmount(() => { cancel(); resize?.disconnect() })
defineExpose({ fit, zoom, focus })
</script>

<template>
  <div
    ref="root"
    class="graph-2d"
    :class="{ 'graph-2d--dragging': dragging, 'graph-2d--linkable': linkable }"
    data-testid="graph-2d"
    tabindex="0"
    aria-label="Graph canvas. Drag the background to pan, scroll to zoom."
    @wheel.prevent="wheel"
    @pointerdown="start($event)"
    @pointermove="move"
    @pointerup="end"
    @pointercancel="cancel"
    @lostpointercapture="cancel"
    @keydown.esc="cancel"
  >
    <div
      class="graph-2d__world"
      :style="{ transform: `translate(${camera.x}px, ${camera.y}px) scale(${camera.zoom})` }"
    >
      <svg
        class="graph-2d__edges"
        width="1"
        height="1"
        aria-label="Connections"
      >
        <!-- One arrowhead per colour a line takes: a marker does not take
             the colour of the line it ends. -->
        <defs><marker
          v-for="tone in ARROW_TONES"
          :id="`${arrowId}-${tone}`"
          :key="tone"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        ><path
          d="M 0 0 L 10 5 L 0 10 z"
          class="graph-2d__arrow"
          :class="`graph-2d__arrow--${tone}`"
        /></marker></defs>
        <g
          v-for="item in paths"
          :key="item.edge.id"
          :class="[item.edge.tone ? `graph-2d__tone--${item.edge.tone}` : '', { 'graph-2d__edge--active': highlighted.has(item.edge.id), 'graph-2d__dim': dimOthers && selection && !highlighted.has(item.edge.id) }]"
          :data-tone="item.edge.tone"
        >
          <path
            :d="item.path"
            class="graph-2d__edge"
            :class="{ 'graph-2d__edge--dashed': item.edge.dashed }"
            :marker-end="item.edge.directed ? `url(#${arrowId}-${arrowTone(item.edge, highlighted.has(item.edge.id))})` : undefined"
          />
          <path
            :d="item.path"
            class="graph-2d__edge-hit"
            tabindex="0"
            role="button"
            data-graph-interactive
            :aria-label="item.edge.label"
            :data-testid="`graph-edge-${item.edge.id}`"
            @pointerdown.stop="emit('select', { kind: 'edge', id: item.edge.id })"
            @keydown.enter.prevent="emit('select', { kind: 'edge', id: item.edge.id })"
          ><title>{{ item.edge.label }}</title></path>
        </g>
        <path
          v-if="draft"
          :d="draft"
          class="graph-2d__edge graph-2d__edge--dashed"
          data-testid="graph-draft-edge"
        />
      </svg>
      <!-- Written over the lines rather than in them, so a number can carry a
           hint of its own; a press on one selects its line. -->
      <template v-if="edgeLabels">
        <span
          v-for="item in labelled"
          :key="item.edge.id"
          class="graph-2d__label"
          :class="{ 'graph-2d__label--active': highlighted.has(item.edge.id), 'graph-2d__dim': dimOthers && selection && !highlighted.has(item.edge.id) }"
          :style="{ left: `${(spots.get(item.edge.id) ?? item.mid).x}px`, top: `${(spots.get(item.edge.id) ?? item.mid).y}px` }"
          :data-testid="`graph-edge-label-${item.edge.id}`"
          data-graph-interactive
          @pointerdown.stop="emit('select', { kind: 'edge', id: item.edge.id })"
        ><span
          v-if="item.edge.badge"
          class="graph-2d__badge"
          :class="{ 'graph-2d__badge--caution': item.edge.caution }"
          :data-testid="`graph-edge-badge-${item.edge.id}`"
        >{{ item.edge.badge }}<AppTooltip v-if="item.edge.caution">{{ item.edge.caution }}</AppTooltip></span>{{
          item.edge.badge && item.edge.label ? " · " : "" }}{{ item.edge.label }}</span>
      </template>
      <article
        v-for="node in graph.nodes"
        :key="node.id"
        class="graph-node"
        :data-testid="`graph-node-${node.id}`"
        :class="{ 'graph-node--selected': selection?.kind === 'node' && selection.id === node.id, 'graph-node--placeholder': node.placeholder, 'graph-2d__dim': dimOthers && selection && !neighbors.has(node.id) }"
        :style="{ left: `${positions[node.id]!.x}px`, top: `${positions[node.id]!.y}px`, width: `${CARD_WIDTH}px`, '--node-accent': `var(--dp-chart-${accentIndex(node)})` }"
        data-graph-interactive
      >
        <div
          class="graph-node__head"
          role="button"
          tabindex="0"
          :aria-label="node.label"
          :style="{ height: `${HEADER_HEIGHT}px` }"
          @pointerdown.stop="start($event, node.id)"
          @dblclick.stop="emit('activate', node.id)"
          @keydown.enter.prevent="emit('select', { kind: 'node', id: node.id })"
        >
          <div class="graph-node__title">
            <strong :title="node.label">{{ node.label }}</strong>
            <span :title="node.caption">{{ node.caption || `${node.rows.length} fields` }}</span>
          </div>
          <!-- A producer's commands for its card. Out of the head's gestures:
               a press here neither drags the card nor selects it. -->
          <span
            v-if="$slots['node-head']"
            class="graph-node__actions"
            data-graph-interactive
            @pointerdown.stop
            @dblclick.stop
            @keydown.stop
          >
            <slot
              name="node-head"
              :node="node"
            />
          </span>
        </div>
        <template v-if="expanded">
          <div
            v-for="row in node.rows"
            :key="row.id"
            class="graph-node__row"
            role="button"
            tabindex="0"
            :class="{ 'graph-node__row--selected': selection?.kind === 'node' && selection.id === node.id && selection.portId === row.id, 'graph-node__row--muted': row.muted, 'graph-node__row--made': row.made, 'graph-node__row--aimed': aimed?.nodeId === node.id && aimed.portId === row.id }"
            :style="{ height: `${ROW_HEIGHT}px` }"
            :aria-label="`${node.label}: ${row.label}`"
            :data-testid="`graph-port-${node.id}-${row.id}`"
            :data-port-node="node.id"
            :data-port-id="row.id"
            @pointerdown.stop="startLink($event, node.id, row.id)"
            @click.stop="pressRow(node.id, row.id)"
            @keydown.enter.prevent="emit('select', { kind: 'node', id: node.id, portId: row.id })"
          >
            <!-- A dot where a line actually arrives, and nowhere else: every
                 row carrying two of them made a card a column of dots. -->
            <span
              v-if="anchorOf(node.id, row.id).left"
              class="graph-node__port graph-node__port--left"
              :data-testid="`graph-anchor-${node.id}-${row.id}`"
            />
            <span
              v-if="anchorOf(node.id, row.id).right"
              class="graph-node__port graph-node__port--right"
              :data-testid="`graph-anchor-${node.id}-${row.id}`"
            />
            <span class="graph-node__badges"><q-icon
              v-if="row.icon"
              :name="row.icon"
              size="14px"
            />{{ row.badges?.join(' ') }}</span>
            <span
              class="graph-node__name"
              :title="row.label"
            >{{ row.label }}</span>
            <span
              class="graph-node__type"
              :title="row.detail"
            >{{ row.detail }}</span>
          </div>
        </template>
      </article>
    </div>
  </div>
</template>

<style scoped>
.graph-2d { position: relative; flex: 1; width: 100%; height: 100%; min-height: 220px; overflow: hidden; touch-action: none; cursor: grab; background: var(--dp-chrome-raised); }
.graph-2d--dragging { cursor: grabbing; user-select: none; }
.graph-2d__world { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.graph-2d__edges { position: absolute; overflow: visible; }
.graph-2d__edge { fill: none; stroke: var(--dp-graph-edge); stroke-width: 1.6; vector-effect: non-scaling-stroke; pointer-events: none; }
.graph-2d__edge--dashed { stroke-dasharray: 5 4; }
.graph-2d__label { position: absolute; transform: translate(-50%, -50%); padding: 0 var(--dp-space-half); border-radius: var(--dp-radius-control); background: var(--dp-chrome-raised); color: var(--dp-text-muted); font-size: 11px; white-space: nowrap; cursor: pointer; }
.graph-2d__label--active { color: var(--dp-text-strong); }
.graph-2d__badge { font-weight: 600; color: var(--dp-text-strong); }
.graph-2d__badge--caution { color: var(--dp-tone-warning-text); cursor: help; }
/* A row is dragged towards another, and selects no text on the way. */
.graph-2d--linkable .graph-node__row { cursor: crosshair; user-select: none; }
.graph-2d__arrow { fill: var(--dp-graph-edge); }
.graph-2d__arrow--active, .graph-2d__arrow--info { fill: var(--dp-accent); }
.graph-2d__arrow--success { fill: var(--dp-content-success); }
.graph-2d__arrow--error { fill: var(--dp-content-error); }
.graph-2d__edge--active .graph-2d__edge { stroke: var(--dp-accent); stroke-width: 2.8; }
/* After the selection's rule: a selected line keeps its result's colour. */
.graph-2d__tone--info .graph-2d__edge { stroke: var(--dp-accent); stroke-width: 2.8; }
.graph-2d__tone--success .graph-2d__edge { stroke: var(--dp-content-success); }
.graph-2d__tone--error .graph-2d__edge { stroke: var(--dp-content-error); }
.graph-2d__tone--muted { opacity: 0.45; }
/* Its own stroke is the mark of focus, and only the keyboard's: a pointer press
   focuses the curve too, and with :focus the fourteen pixels showed as a grey
   band, while the browser's ring drew a rectangle round the whole curve. */
.graph-2d__edge-hit { fill: none; stroke: transparent; stroke-width: 14; vector-effect: non-scaling-stroke; pointer-events: stroke; cursor: pointer; outline: none; }
.graph-2d__edge-hit:focus-visible { stroke: var(--dp-focus-border); }
.graph-2d__dim { opacity: 0.3; }
.graph-node { position: absolute; border: 1px solid var(--dp-border-strong); border-radius: var(--dp-radius-panel); background: var(--dp-surface); box-shadow: 0 3px 12px var(--dp-border-faint); box-sizing: border-box; }
.graph-node--selected { outline: 2px solid var(--dp-accent); }
.graph-node--placeholder { border-style: dashed; }
.graph-node__head { display: flex; align-items: center; gap: var(--dp-space-1); padding: var(--dp-space-1) var(--dp-space-1) var(--dp-space-1) var(--dp-space-3); border-top: 4px solid var(--node-accent); border-radius: var(--dp-radius-panel) var(--dp-radius-panel) 0 0; background: var(--dp-chrome); box-sizing: border-box; cursor: grab; }
.graph-node__title { flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; gap: var(--dp-space-half); }
.graph-node__title strong { font-size: 13px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.graph-node__title > span { color: var(--dp-text-muted); font-size: 10px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.graph-node__actions { flex: none; display: flex; align-items: center; cursor: default; }
.graph-node__row { display: flex; position: relative; align-items: center; gap: var(--dp-space-2); padding: 0 var(--dp-space-2); border-top: 1px solid var(--dp-border-faint); box-sizing: border-box; font-size: 11px; cursor: pointer; }
.graph-node__row:hover, .graph-node__row--selected, .graph-node__row--aimed { background: var(--dp-selected); }
.graph-node__head:focus-visible, .graph-node__row:focus-visible { outline: 2px solid var(--dp-accent); }
.graph-node__badges { flex: 0 0 34px; display: flex; align-items: center; color: var(--node-accent); font-size: 9px; font-weight: 600; }
.graph-node__row--muted .graph-node__name { color: var(--dp-text-muted); text-decoration: line-through; }
.graph-node__row--made .graph-node__name { font-style: italic; }
.graph-node__name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.graph-node__type { max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--dp-text-muted); font-family: var(--dp-font-mono); font-size: 10px; }
.graph-node__port { position: absolute; width: 5px; height: 5px; border-radius: 50%; background: var(--node-accent); top: calc(50% - 2.5px); }
.graph-node__port--left { left: -3px; } .graph-node__port--right { right: -3px; }
</style>
