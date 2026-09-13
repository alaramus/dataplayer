<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"

import { GRID_COLUMNS, gridRows, moveItem, resizeItem } from "./gridLayout"
import type { Box, Placed } from "./gridLayout"

/**
 * Where widgets stand, and the gestures that move and resize them.
 *
 * The arithmetic is `gridLayout.ts`; this only turns pixels into cells. While a
 * widget is carried every widget is drawn where the layout would put it, so
 * what the release will do is what is on screen.
 */
const props = defineProps<{
  items: Placed[]
  /** One widget filling the grid; the others are hidden, not unmounted. */
  expandedId: string | null
}>()

const emit = defineEmits<{ layout: [items: Placed[]] }>()

const ROW_HEIGHT = 40
const GAP = 8

const host = ref<HTMLElement | null>(null)
const width = ref(0)
const preview = ref<Placed[] | null>(null)
let observer: ResizeObserver | null = null

type Gesture = { kind: "move" | "resize"; id: string; startX: number; startY: number; box: Box }
let gesture: Gesture | null = null

const shown = computed(() => preview.value ?? props.items)
const column = computed(() => Math.max(1, (width.value - GAP * (GRID_COLUMNS - 1)) / GRID_COLUMNS))
const height = computed(() => {
  const rows = gridRows(shown.value)
  return rows === 0 ? 0 : rows * (ROW_HEIGHT + GAP) - GAP
})

function styleOf(box: Box) {
  if (props.expandedId !== null) return { left: "0", top: "0", width: "100%", height: "100%" }
  return {
    left: `${String(box.x * (column.value + GAP))}px`,
    top: `${String(box.y * (ROW_HEIGHT + GAP))}px`,
    width: `${String(box.w * column.value + (box.w - 1) * GAP)}px`,
    height: `${String(box.h * ROW_HEIGHT + (box.h - 1) * GAP)}px`,
  }
}

function begin(kind: Gesture["kind"], id: string, event: PointerEvent) {
  if (props.expandedId !== null || event.button !== 0) return
  const item = props.items.find((one) => one.id === id)
  if (item === undefined) return
  event.preventDefault()
  gesture = { kind, id, startX: event.clientX, startY: event.clientY, box: item.layout }
  window.addEventListener("pointermove", onMove)
  window.addEventListener("pointerup", onUp)
  window.addEventListener("pointercancel", onCancel)
}

function onMove(event: PointerEvent) {
  if (gesture === null) return
  const dx = Math.round((event.clientX - gesture.startX) / (column.value + GAP))
  const dy = Math.round((event.clientY - gesture.startY) / (ROW_HEIGHT + GAP))
  preview.value = gesture.kind === "move"
    ? moveItem(props.items, gesture.id, { x: gesture.box.x + dx, y: gesture.box.y + dy })
    : resizeItem(props.items, gesture.id, { w: gesture.box.w + dx, h: gesture.box.h + dy })
}

function stop() {
  gesture = null
  window.removeEventListener("pointermove", onMove)
  window.removeEventListener("pointerup", onUp)
  window.removeEventListener("pointercancel", onCancel)
}

function onUp() {
  const next = preview.value
  stop()
  preview.value = null
  if (next !== null && JSON.stringify(next) !== JSON.stringify(props.items)) emit("layout", next)
}

function onCancel() {
  stop()
  preview.value = null
}

onMounted(() => {
  if (host.value === null) return
  width.value = host.value.clientWidth
  observer = new ResizeObserver(() => {
    width.value = host.value?.clientWidth ?? 0
  })
  observer.observe(host.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  stop()
})

defineExpose({ begin })
</script>

<template>
  <div
    ref="host"
    class="dashboard-grid"
    :class="{ 'dashboard-grid--expanded': expandedId !== null, 'dashboard-grid--carrying': preview !== null }"
    :style="expandedId === null ? { height: `${height}px` } : undefined"
    data-testid="dashboard-grid"
  >
    <div
      v-for="item in shown"
      v-show="expandedId === null || expandedId === item.id"
      :key="item.id"
      class="dashboard-grid__item"
      :style="styleOf(item.layout)"
    >
      <slot
        :id="item.id"
        :grab="(event: PointerEvent) => begin('move', item.id, event)"
        :grab-resize="(event: PointerEvent) => begin('resize', item.id, event)"
      />
    </div>
  </div>
</template>

<style scoped>
.dashboard-grid {
  position: relative;
  width: 100%;
}

.dashboard-grid--expanded {
  height: 100%;
}

.dashboard-grid--carrying {
  user-select: none;
}

.dashboard-grid__item {
  position: absolute;
  box-sizing: border-box;
}
</style>
