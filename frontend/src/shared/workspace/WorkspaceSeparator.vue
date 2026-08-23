<script setup lang="ts">
import { ref } from "vue"

import { PRESS_THRESHOLD_PX } from "./model"
import type { Direction } from "./model"

const props = defineProps<{ direction: Direction }>()
const emit = defineEmits<{ move: [deltaPx: number]; toggle: [] }>()

const dragging = ref(false)
let origin = 0
let moved = 0

function onPointerDown(event: PointerEvent) {
  ;(event.target as HTMLElement).setPointerCapture(event.pointerId)
  dragging.value = true
  moved = 0
  origin = props.direction === "row" ? event.clientX : event.clientY
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value) return
  const now = props.direction === "row" ? event.clientX : event.clientY
  const delta = now - origin
  origin = now
  moved += Math.abs(delta)
  emit("move", delta)
}

function onPointerUp(event: PointerEvent) {
  if (!dragging.value) return
  ;(event.target as HTMLElement).releasePointerCapture(event.pointerId)
  dragging.value = false
  // A border that was pressed rather than dragged is the handle that brings a
  // collapsed section back, which is why a collapsed section keeps its border.
  if (moved < PRESS_THRESHOLD_PX) emit("toggle")
}
</script>

<template>
  <div
    class="workspace-separator"
    :class="direction === 'row' ? 'workspace-separator--row' : 'workspace-separator--column'"
    data-testid="workspace-separator"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
  />
</template>

<style scoped>
.workspace-separator {
  flex: 0 0 5px;
  background: var(--dp-separator);
}
.workspace-separator--row {
  cursor: col-resize;
}
.workspace-separator--column {
  cursor: row-resize;
}
.workspace-separator:hover {
  background: var(--dp-separator-active);
}
</style>
