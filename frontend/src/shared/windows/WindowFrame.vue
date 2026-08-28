<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue"

import { AppIconButton } from "@/shared/ui"

import type { WindowState } from "./useWindows"
import type { ResizeEdge } from "./geometry"

/**
 * The chrome of one floating window: a bar to drag it by, and a cross.
 *
 * Dragging is pointer events rather than a directive: a pointer capture keeps
 * the window following the cursor when it leaves the bar, which is what makes
 * a fast drag not lose the window halfway.
 */
const props = defineProps<{ window: WindowState; front: boolean }>()

const emit = defineEmits<{
  focus: []
  close: []
  move: [to: { x: number; y: number }]
  resize: [edge: ResizeEdge, pointer: { x: number; y: number }]
  fit: [size: { width: number; height: number }]
}>()

const dragging = ref(false)
let grabbedAt = { x: 0, y: 0 }
const frame = ref<HTMLElement | null>(null)
const body = ref<HTMLElement | null>(null)
let observer: ResizeObserver | null = null

function startDrag(event: PointerEvent) {
  // Only the primary button, and never from a control inside the bar.
  if (event.button !== 0) return
  emit("focus")
  dragging.value = true
  grabbedAt = { x: event.clientX - props.window.rect.x, y: event.clientY - props.window.rect.y }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function onDrag(event: PointerEvent) {
  if (!dragging.value) return
  emit("move", { x: event.clientX - grabbedAt.x, y: event.clientY - grabbedAt.y })
}

function endDrag(event: PointerEvent) {
  if (!dragging.value) return
  dragging.value = false
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

function measure() {
  if (props.window.autoFit === false || frame.value === null || body.value === null) return
  const bar = frame.value.querySelector<HTMLElement>(".app-window__bar")
  emit("fit", {
    width: Math.ceil(Math.max(props.window.rect.width, body.value.scrollWidth + 2)),
    height: Math.ceil((bar?.offsetHeight ?? 0) + body.value.scrollHeight + 2),
  })
}

onMounted(async () => {
  await nextTick()
  window.requestAnimationFrame(measure)
  if (typeof ResizeObserver !== "undefined" && body.value !== null) {
    observer = new ResizeObserver(measure)
    observer.observe(body.value)
    if (body.value.firstElementChild) observer.observe(body.value.firstElementChild)
  }
})

onBeforeUnmount(() => observer?.disconnect())

function startResize(edge: ResizeEdge, event: PointerEvent) {
  if (event.button !== 0) return
  emit("focus")
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
  const move = (next: PointerEvent) => emit("resize", edge, { x: next.clientX, y: next.clientY })
  const finish = () => {
    target.removeEventListener("pointermove", move)
    target.removeEventListener("pointerup", finish)
    target.removeEventListener("pointercancel", finish)
  }
  target.addEventListener("pointermove", move)
  target.addEventListener("pointerup", finish)
  target.addEventListener("pointercancel", finish)
}

const resizeEdges: ResizeEdge[] = [
  "top",
  "right",
  "bottom",
  "left",
  "top-left",
  "top-right",
  "bottom-left",
  "bottom-right",
]
</script>

<template>
  <section
    ref="frame"
    class="app-window"
    :class="{ 'app-window--front': front }"
    :style="{
      left: `${window.rect.x}px`,
      top: `${window.rect.y}px`,
      width: `${window.rect.width}px`,
      height: window.autoFit !== false && !window.hasFit ? 'auto' : `${window.rect.height}px`,
    }"
    :data-testid="`window-${window.id}`"
    role="dialog"
    :aria-label="window.look.title"
    @pointerdown="emit('focus')"
  >
    <header
      class="app-window__bar"
      :class="{ 'app-window__bar--dragging': dragging }"
      :data-testid="`window-bar-${window.id}`"
      @pointerdown="startDrag"
      @pointermove="onDrag"
      @pointerup="endDrag"
      @pointercancel="endDrag"
    >
      <q-icon
        v-if="window.look.icon"
        :name="window.look.icon"
        size="18px"
      />
      <span class="app-window__title">{{ window.look.title }}</span>
      <!-- Wrapped so the drag handler above does not see the press. -->
      <span @pointerdown.stop>
        <AppIconButton
          icon="close"
          tooltip="Close"
          :data-testid="`window-close-${window.id}`"
          @click="emit('close')"
        />
      </span>
    </header>

    <div
      ref="body"
      class="app-window__body"
    >
      <component :is="window.component" />
    </div>
    <span
      v-for="edge in resizeEdges"
      :key="edge"
      class="app-window__resize"
      :class="`app-window__resize--${edge}`"
      :data-testid="`window-resize-${edge}-${window.id}`"
      @pointerdown.stop="startResize(edge, $event)"
    />
  </section>
</template>

<style scoped>
.app-window {
  box-sizing: border-box;
  position: fixed;
  max-width: 100vw;
  max-height: 100vh;
  /* Named rather than numbered: what a window has to clear and what it has to
     stay under is stated once, in `shared/ui/layers.css`. */
  z-index: var(--dp-layer-window);
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--dp-surface-raised);
  border: 1px solid var(--dp-border-strong);
  border-radius: 6px;
  box-shadow: 0 6px 24px var(--dp-shadow);
  overflow: hidden;
}
.app-window--front {
  box-shadow: 0 10px 40px var(--dp-shadow-strong);
  border-color: var(--dp-focus-border);
}
.app-window__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 4px 4px 10px;
  background: var(--dp-active);
  cursor: grab;
  /* Otherwise a drag selects the title text instead of moving the window. */
  user-select: none;
  touch-action: none;
}
.app-window__bar--dragging {
  cursor: grabbing;
}
.app-window__title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.app-window__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.app-window__resize {
  position: absolute;
  touch-action: none;
}
.app-window__resize--top,
.app-window__resize--bottom {
  left: 8px;
  right: 8px;
  height: 7px;
  cursor: ns-resize;
}
.app-window__resize--top { top: -1px; }
.app-window__resize--bottom { bottom: -1px; }
.app-window__resize--left,
.app-window__resize--right {
  top: 8px;
  bottom: 8px;
  width: 7px;
  cursor: ew-resize;
}
.app-window__resize--left { left: -1px; }
.app-window__resize--right { right: -1px; }
.app-window__resize--top-left,
.app-window__resize--top-right,
.app-window__resize--bottom-left,
.app-window__resize--bottom-right {
  width: 12px;
  height: 12px;
}
.app-window__resize--top-left { top: -1px; left: -1px; cursor: nwse-resize; }
.app-window__resize--top-right { top: -1px; right: -1px; cursor: nesw-resize; }
.app-window__resize--bottom-left { bottom: -1px; left: -1px; cursor: nesw-resize; }
.app-window__resize--bottom-right { bottom: -1px; right: -1px; cursor: nwse-resize; }
</style>
