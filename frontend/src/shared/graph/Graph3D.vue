<script setup lang="ts">
import { onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue"

import { t } from "@/shared/i18n"
import { AppBanner } from "@/shared/ui"
import type { Camera3, GraphDocument, GraphSelection, Point3 } from "./model"
import { GraphScene } from "./scene3d"

const props = defineProps<{ graph: GraphDocument; positions: Record<string, Point3>; camera: Camera3 | null; selection: GraphSelection; labels: boolean }>()
const emit = defineEmits<{ camera: [value: Camera3]; move: [id: string, position: Point3]; select: [value: GraphSelection]; activate: [id: string] }>()
const root = ref<HTMLDivElement>()
const unavailable = ref(false)
let scene: GraphScene | undefined
onMounted(() => {
  try {
    scene = new GraphScene(root.value!, {
      camera: (value) => emit("camera", value), move: (id, value) => emit("move", id, value),
      select: (value) => emit("select", value), activate: (id) => emit("activate", id),
      unavailable: () => { unavailable.value = true; scene?.setActive(false) },
    }, props.camera)
    scene.setGraph(props.graph, props.positions)
    scene.setSelection(props.selection)
    scene.setLabels(props.labels)
    if (!props.camera) scene.fit()
  } catch {
    scene?.dispose(); scene = undefined
    unavailable.value = true
  }
})
watch(() => props.graph, () => scene?.setGraph(props.graph, props.positions))
watch(() => props.positions, (value) => scene?.setPositions(value))
watch(() => props.selection, (value) => scene?.setSelection(value))
watch(() => props.labels, (value) => scene?.setLabels(value))
watch(() => props.camera, (value) => { if (value) scene?.restoreCamera(value); else scene?.fit() })
onActivated(() => { if (!unavailable.value) scene?.setActive(true) })
onDeactivated(() => scene?.setActive(false))
onBeforeUnmount(() => { scene?.dispose(); scene = undefined })
defineExpose({ fit: () => scene?.fit(), zoom: (factor: number) => scene?.zoom(factor), focus: (id: string) => scene?.focus(id) })
</script>

<template>
  <div
    class="graph-3d"
    data-testid="graph-3d"
  >
    <AppBanner
      v-if="unavailable"
      tone="warning"
      data-testid="graph-3d-unavailable"
    >
      {{ t("graph.unavailable_3d") }}
    </AppBanner>
    <div
      v-show="!unavailable"
      ref="root"
      class="graph-3d__surface"
      tabindex="0"
    />
  </div>
</template>

<style scoped>
.graph-3d { width: 100%; height: 100%; min-height: 220px; }
.graph-3d__surface { width: 100%; height: 100%; overflow: hidden; }
.graph-3d__surface :deep(canvas) { display: block; touch-action: none; }
</style>
