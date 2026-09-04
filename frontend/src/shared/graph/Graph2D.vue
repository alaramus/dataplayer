<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, useId } from "vue"

import { CARD_WIDTH, HEADER_HEIGHT, ROW_HEIGHT, edgePaths, fit2, portAnchors, zoomAt } from "./layout"
import { accentIndex, edgesOf, neighborsOf } from "./model"
import type { Camera2, GraphDocument, GraphSelection, Point2 } from "./model"

const props = defineProps<{
  graph: GraphDocument
  positions: Record<string, Point2>
  camera: Camera2 | null
  expanded: boolean
  selection: GraphSelection
}>()
const emit = defineEmits<{
  camera: [value: Camera2]
  move: [id: string, position: Point2]
  select: [value: GraphSelection]
  activate: [id: string]
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
const arrowId = `graph-arrow-${useId()}`
const dragging = ref(false)
let resize: ResizeObserver | undefined
let gesture: { pointer: number; capture: HTMLElement; start: Point2; camera: Camera2; node?: { id: string; position: Point2 }; moved: boolean } | null = null

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
  if (!gesture || gesture.pointer !== event.pointerId) return
  const ended = gesture
  gesture = null
  dragging.value = false
  if (ended.capture.hasPointerCapture(event.pointerId)) ended.capture.releasePointerCapture(event.pointerId)
  if (!ended.moved) emit("select", ended.node ? { kind: "node", id: ended.node.id } : null)
}
function cancel() {
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
    :class="{ 'graph-2d--dragging': dragging }"
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
        <defs><marker
          :id="arrowId"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        ><path
          d="M 0 0 L 10 5 L 0 10 z"
          class="graph-2d__arrow"
        /></marker></defs>
        <g
          v-for="item in paths"
          :key="item.edge.id"
          :class="{ 'graph-2d__edge--active': highlighted.has(item.edge.id), 'graph-2d__dim': selection && !highlighted.has(item.edge.id) }"
        >
          <path
            :d="item.path"
            class="graph-2d__edge"
            :class="{ 'graph-2d__edge--dashed': item.edge.dashed }"
            :marker-end="item.edge.directed ? `url(#${arrowId})` : undefined"
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
      </svg>
      <article
        v-for="node in graph.nodes"
        :key="node.id"
        class="graph-node"
        :data-testid="`graph-node-${node.id}`"
        :class="{ 'graph-node--selected': selection?.kind === 'node' && selection.id === node.id, 'graph-node--placeholder': node.placeholder, 'graph-2d__dim': selection && !neighbors.has(node.id) }"
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
          <strong :title="node.label">{{ node.label }}</strong>
          <span :title="node.caption">{{ node.caption || `${node.rows.length} fields` }}</span>
        </div>
        <template v-if="expanded">
          <div
            v-for="row in node.rows"
            :key="row.id"
            class="graph-node__row"
            role="button"
            tabindex="0"
            :class="{ 'graph-node__row--selected': selection?.kind === 'node' && selection.id === node.id && selection.portId === row.id }"
            :style="{ height: `${ROW_HEIGHT}px` }"
            :aria-label="`${node.label}: ${row.label}`"
            :data-testid="`graph-port-${node.id}-${row.id}`"
            @pointerdown.stop
            @click.stop="emit('select', { kind: 'node', id: node.id, portId: row.id })"
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
            <span class="graph-node__badges">{{ row.badges?.join(' ') }}</span>
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
.graph-2d__arrow { fill: var(--dp-graph-edge); }
.graph-2d__edge--active .graph-2d__edge { stroke: var(--q-primary); stroke-width: 2.8; }
.graph-2d__edge-hit { fill: none; stroke: transparent; stroke-width: 14; vector-effect: non-scaling-stroke; pointer-events: stroke; cursor: pointer; }
.graph-2d__edge-hit:focus { stroke: var(--dp-focus-border); }
.graph-2d__dim { opacity: 0.3; }
.graph-node { position: absolute; border: 1px solid var(--dp-border-strong); border-radius: 7px; background: var(--dp-surface); box-shadow: 0 3px 12px var(--dp-border-faint); box-sizing: border-box; }
.graph-node--selected { outline: 2px solid var(--q-primary); }
.graph-node--placeholder { border-style: dashed; }
.graph-node__head { display: flex; flex-direction: column; justify-content: center; gap: 2px; padding: 5px 12px; border-top: 4px solid var(--node-accent); border-radius: 6px 6px 0 0; background: var(--dp-chrome); box-sizing: border-box; cursor: grab; }
.graph-node__head strong { font-size: 13px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.graph-node__head > span { color: var(--dp-muted); font-size: 10px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.graph-node__row { display: flex; position: relative; align-items: center; gap: 6px; padding: 0 10px; border-top: 1px solid var(--dp-border-faint); box-sizing: border-box; font-size: 11px; cursor: pointer; }
.graph-node__row:hover, .graph-node__row--selected { background: var(--dp-selected); }
.graph-node__head:focus-visible, .graph-node__row:focus-visible { outline: 2px solid var(--q-primary); }
.graph-node__badges { flex: 0 0 34px; color: var(--node-accent); font-size: 9px; font-weight: 600; }
.graph-node__name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.graph-node__type { max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--dp-muted); font-family: monospace; font-size: 10px; }
.graph-node__port { position: absolute; width: 5px; height: 5px; border-radius: 50%; background: var(--node-accent); top: calc(50% - 2.5px); }
.graph-node__port--left { left: -3px; } .graph-node__port--right { right: -3px; }
</style>
