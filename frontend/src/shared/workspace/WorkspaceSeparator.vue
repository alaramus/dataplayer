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
/* The space between two cards, and the handle that resizes them: the same
   thing, as wide as the inset around the workspace so that the gaps inside it
   and the margin around it are one distance. Never drawn, on hover no more
   than at rest: the cursor already says the gap can be dragged, and a line
   down it would be the frame the cards were made to replace. */
.workspace-separator {
  position: relative;
  z-index: var(--dp-layer-handle);
  flex: 0 0 var(--dp-workspace-inset);
}
/* The target reaches past the gap over the border and the first pixel inside
   either card: the gap alone was a target the pointer often missed. No
   further, because a scrollbar stands against the border and would lose more
   than its outer pixel. */
.workspace-separator::before {
  content: "";
  position: absolute;
}
.workspace-separator--row {
  cursor: col-resize;
}
.workspace-separator--row::before {
  inset: 0 calc(-1 * var(--dp-space-half));
}
.workspace-separator--column {
  cursor: row-resize;
}
.workspace-separator--column::before {
  inset: calc(-1 * var(--dp-space-half)) 0;
}
</style>
