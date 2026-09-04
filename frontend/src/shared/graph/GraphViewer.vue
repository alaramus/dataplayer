<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref, watch } from "vue"

import { AppBanner, AppButton, AppIconButton, AppInput, AppProgress, AppSelect } from "@/shared/ui"
import Graph2D from "./Graph2D.vue"
import { edgesOf, graphProblem, groupGraph } from "./model"
import type { GraphDocument, GraphSelection, GraphViewState, Point2, Point3 } from "./model"

const Graph3D = defineAsyncComponent(() => import("./Graph3D.vue"))
const props = defineProps<{ graph: GraphDocument }>()
const view = defineModel<GraphViewState>({ required: true })
const emit = defineEmits<{ activate: [nodeId: string] }>()
const selection = ref<GraphSelection>(null)
const search = ref("")
const loading = ref(false)
const layoutError = ref("")
const surface = ref<{ fit: () => void; zoom: (factor: number) => void; focus: (id: string) => void }>()
const problem = computed(() => graphProblem(props.graph))
const graph = computed(() => groupGraph(props.graph, view.value.groupId))
const ready = computed(() => props.graph.nodes.every((node) => Object.hasOwn(view.value.positions2, node.id) && Object.hasOwn(view.value.positions3, node.id)))
const matches = computed(() => {
  const needle = search.value.trim().toLowerCase()
  return needle ? graph.value.nodes.filter((node) => [node.label, node.caption ?? "", ...node.rows.map((row) => row.label)].some((value) => value.toLowerCase().includes(needle))).slice(0, 30) : []
})
const groups = computed(() => [{ label: "All groups", value: "" }, ...props.graph.groups.map((group) => ({ label: group.label, value: group.id }))])
const selectedNode = computed(() => selection.value?.kind === "node" ? props.graph.nodes.find((node) => node.id === selection.value?.id) : undefined)
const selectedEdge = computed(() => selection.value?.kind === "edge" ? props.graph.edges.find((edge) => edge.id === selection.value?.id) : undefined)
const related = computed(() => edgesOf(props.graph, selection.value))
const nameOf = (id: string) => props.graph.nodes.find((node) => node.id === id)?.label ?? id
let worker: Worker | undefined
let timeout: ReturnType<typeof setTimeout> | undefined

function patch(values: Partial<GraphViewState>) { view.value = { ...view.value, ...values } }
function stopLayout() {
  worker?.terminate(); worker = undefined
  if (timeout !== undefined) clearTimeout(timeout)
  timeout = undefined
  loading.value = false
}
function cancelLayout() { stopLayout(); layoutError.value = "Layout cancelled. Use Arrange to try again." }
function arrange(force?: "2d" | "3d") {
  stopLayout()
  if (problem.value || !props.graph.nodes.length) return
  loading.value = true
  layoutError.value = ""
  try {
    worker = new Worker(new URL("./layout.worker.ts", import.meta.url), { type: "module" })
    worker.onmessage = (event: MessageEvent<{ result?: { positions2: Record<string, Point2>; positions3: Record<string, Point3> }; error?: string }>) => {
      const result = event.data.result
      if (result) {
        const positions2 = Object.fromEntries(props.graph.nodes.map((node) => [node.id, force !== "2d" && Object.hasOwn(view.value.positions2, node.id) ? view.value.positions2[node.id]! : result.positions2[node.id]!]))
        const positions3 = Object.fromEntries(props.graph.nodes.map((node) => [node.id, force !== "3d" && Object.hasOwn(view.value.positions3, node.id) ? view.value.positions3[node.id]! : result.positions3[node.id]!]))
        patch({ positions2, positions3, ...(force === "2d" ? { camera2: null } : {}), ...(force === "3d" ? { camera3: null } : {}) })
        if (force) void nextTick(() => surface.value?.fit())
      } else layoutError.value = event.data.error ?? "This graph could not be arranged."
      stopLayout()
    }
    worker.onerror = () => { layoutError.value = "This graph could not be arranged. Try a smaller selection."; stopLayout() }
    timeout = setTimeout(() => { layoutError.value = "Arranging took too long. Try a smaller selection."; stopLayout() }, 20_000)
    // Vue proxies do not cross a worker boundary. The document contains only
    // bounded presentation data; neither callbacks nor source objects cross.
    worker.postMessage({ graph: JSON.parse(JSON.stringify(props.graph)), expanded: view.value.expanded })
  } catch {
    layoutError.value = "The layout worker could not be started."
    stopLayout()
  }
}
function chooseGroup(value: unknown) {
  const groupId = typeof value === "string" && value ? value : null
  patch({ groupId })
  selection.value = null
  void nextTick(() => surface.value?.fit())
}
function select(value: GraphSelection, focus = false) {
  selection.value = value
  if (focus && value?.kind === "node") void nextTick(() => surface.value?.focus(value.id))
}
function searchPick(id: string) { search.value = ""; select({ kind: "node", id }, true) }
function moved2(id: string, position: Point2) { patch({ positions2: { ...view.value.positions2, [id]: position } }) }
function moved3(id: string, position: Point3) { patch({ positions3: { ...view.value.positions3, [id]: position } }) }
watch(() => props.graph, () => {
  if (view.value.groupId && !props.graph.groups.some((group) => group.id === view.value.groupId)) patch({ groupId: null })
  if (selection.value && ![...props.graph.nodes, ...props.graph.edges].some((item) => item.id === selection.value?.id)) selection.value = null
  arrange()
}, { immediate: true })
watch(ready, (value) => { if (!value && !loading.value) arrange() })
onBeforeUnmount(stopLayout)
</script>

<template>
  <div class="graph-viewer" data-testid="graph-viewer">
    <div class="graph-viewer__toolbar">
      <AppButton label="2D" size="sm" :variant="view.mode === '2d' ? 'primary' : 'quiet'" :aria-pressed="view.mode === '2d'" data-testid="graph-mode-2d" @click="patch({ mode: '2d' })" />
      <AppButton label="3D" size="sm" :variant="view.mode === '3d' ? 'primary' : 'quiet'" :aria-pressed="view.mode === '3d'" data-testid="graph-mode-3d" @click="patch({ mode: '3d' })" />
      <q-separator vertical inset />
      <AppIconButton icon="center_focus_strong" tooltip="Fit graph" data-testid="graph-fit" :disable="!ready" @click="surface?.fit()" />
      <AppIconButton icon="add" tooltip="Zoom in" :disable="!ready" @click="surface?.zoom(1.25)" />
      <AppIconButton icon="remove" tooltip="Zoom out" :disable="!ready" @click="surface?.zoom(0.8)" />
      <AppIconButton icon="auto_awesome_mosaic" tooltip="Arrange this view" data-testid="graph-arrange" :disable="Boolean(problem) || loading" @click="arrange(view.mode)" />
      <AppIconButton v-if="view.mode === '2d'" :icon="view.expanded ? 'unfold_less' : 'unfold_more'" :tooltip="view.expanded ? 'Collapse fields' : 'Show fields'" data-testid="graph-details-toggle" @click="patch({ expanded: !view.expanded })" />
      <AppIconButton v-else :icon="view.labels ? 'label_off' : 'label'" :tooltip="view.labels ? 'Hide labels' : 'Show labels'" @click="patch({ labels: !view.labels })" />
      <AppSelect v-if="graph.groups.length" :model-value="view.groupId ?? ''" :options="groups" compact aria-label="Graph group" data-testid="graph-group" class="graph-viewer__group" @update:model-value="chooseGroup" />
      <div class="graph-viewer__search">
        <AppInput v-model="search" compact clearable placeholder="Find a node or field" aria-label="Find a node or field" data-testid="graph-search" />
        <div v-if="search.trim()" class="graph-viewer__matches" role="list" aria-label="Matching nodes">
          <AppButton v-for="node in matches" :key="node.id" variant="quiet" :label="node.label" size="sm" @click="searchPick(node.id)" />
          <span v-if="!matches.length">No matching nodes</span>
        </div>
      </div>
    </div>
    <div v-if="loading" class="graph-viewer__loading" role="status">
      <span>Arranging graph…</span><AppProgress label="Arranging graph" /><AppIconButton icon="close" tooltip="Cancel layout" @click="cancelLayout" />
    </div>
    <AppBanner v-if="problem || layoutError" tone="warning" data-testid="graph-error">{{ problem || layoutError }}</AppBanner>
    <div v-if="!problem && ready && graph.nodes.length" class="graph-viewer__body">
      <div class="graph-viewer__canvas">
        <Graph2D v-if="view.mode === '2d'" ref="surface" :graph="graph" :positions="view.positions2" :camera="view.camera2" :selection="selection" :expanded="view.expanded" @camera="patch({ camera2: $event })" @move="moved2" @select="select" @activate="emit('activate', $event)" />
        <Graph3D v-else ref="surface" :graph="graph" :positions="view.positions3" :camera="view.camera3" :selection="selection" :labels="view.labels" @camera="patch({ camera3: $event })" @move="moved3" @select="select" @activate="emit('activate', $event)" />
      </div>
      <aside v-if="selection" class="graph-viewer__inspector" data-testid="graph-inspector" aria-label="Selection details">
        <div class="graph-viewer__inspector-head"><strong>{{ selectedNode?.label ?? selectedEdge?.label }}</strong><AppIconButton icon="close" tooltip="Clear selection" @click="select(null)" /></div>
        <template v-if="selectedNode">
          <p>{{ selectedNode.caption }}</p>
          <slot name="node-actions" :node="selectedNode" />
          <dl><template v-for="(detail, index) in selectedNode.details" :key="index"><dt>{{ detail.label }}</dt><dd>{{ detail.value }}</dd></template></dl>
          <div v-for="row in selectedNode.rows" :key="row.id" class="graph-viewer__field" :class="{ 'graph-viewer__field--selected': selection.kind === 'node' && selection.portId === row.id }">
            <AppButton variant="quiet" size="sm" :label="row.label" @click="select({ kind: 'node', id: selectedNode.id, portId: row.id })" />
            <small>{{ row.badges?.join(' · ') }} {{ row.detail }}</small>
          </div>
        </template>
        <template v-if="selectedEdge">
          <AppButton variant="quiet" size="sm" :label="`From: ${nameOf(selectedEdge.source.nodeId)}`" @click="select({ kind: 'node', id: selectedEdge.source.nodeId }, true)" />
          <AppButton variant="quiet" size="sm" :label="`To: ${nameOf(selectedEdge.target.nodeId)}`" @click="select({ kind: 'node', id: selectedEdge.target.nodeId }, true)" />
          <dl><template v-for="(detail, index) in selectedEdge.details" :key="index"><dt>{{ detail.label }}</dt><dd>{{ detail.value }}</dd></template></dl>
        </template>
        <div v-if="selectedNode" class="graph-viewer__connections">
          <strong>Connections · {{ related.length }}</strong>
          <AppButton v-for="edge in related" :key="edge.id" variant="quiet" size="sm" :label="edge.label" @click="select({ kind: 'edge', id: edge.id })" />
          <span v-if="!related.length">No connections in this graph</span>
        </div>
      </aside>
    </div>
    <div v-else-if="!loading && !problem && !layoutError" class="graph-viewer__empty">No nodes to display</div>
    <div class="graph-viewer__foot"><span>{{ graph.nodes.length }} nodes · {{ graph.edges.length }} connections</span><span>{{ view.mode === '2d' ? 'Drag cards to move · Drag canvas to pan · Scroll to zoom' : 'Drag to orbit · Right-drag to pan · Shift-drag to move a node' }}</span></div>
  </div>
</template>

<style scoped>
.graph-viewer { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.graph-viewer__toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; padding: 5px 7px; border-bottom: 1px solid var(--dp-border); }
.graph-viewer__group { min-width: 110px; max-width: 170px; }
.graph-viewer__search { position: relative; flex: 1; min-width: 150px; }
.graph-viewer__matches { position: absolute; top: 100%; left: 0; right: 0; z-index: var(--dp-layer-popover); background: var(--dp-surface-raised); border: 1px solid var(--dp-border-strong); display: flex; flex-direction: column; max-height: 300px; overflow-y: auto; padding: 6px; }
.graph-viewer__body { display: flex; flex: 1; min-height: 0; }
.graph-viewer__canvas { flex: 1; min-width: 0; overflow: hidden; }
.graph-viewer__inspector { width: 270px; max-width: 40%; flex-shrink: 0; padding: 10px; border-left: 1px solid var(--dp-border); overflow: auto; font-size: 12px; overflow-wrap: anywhere; }
.graph-viewer__inspector-head { display: flex; justify-content: space-between; align-items: start; gap: 5px; }
.graph-viewer__inspector-head strong { font-size: 14px; }
.graph-viewer__inspector p, .graph-viewer__inspector small { color: var(--dp-muted); }
.graph-viewer__inspector dt { color: var(--dp-muted); margin-top: 8px; }
.graph-viewer__inspector dd { margin: 2px 0; white-space: pre-wrap; }
.graph-viewer__field { display: flex; flex-direction: column; align-items: start; border-bottom: 1px solid var(--dp-border-faint); padding: 3px 0; }
.graph-viewer__field--selected { background: var(--dp-selected); }
.graph-viewer__field small { padding: 0 8px 4px; }
.graph-viewer__connections { display: flex; flex-direction: column; gap: 4px; margin-top: 16px; }
.graph-viewer__loading { display: flex; gap: 10px; align-items: center; padding: 3px 8px; font-size: 12px; }
.graph-viewer__loading > span { white-space: nowrap; }
.graph-viewer__foot { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; padding: 4px 8px; border-top: 1px solid var(--dp-border); color: var(--dp-muted); font-size: 10px; }
.graph-viewer__empty { flex: 1; display: grid; place-content: center; color: var(--dp-muted); }
</style>
