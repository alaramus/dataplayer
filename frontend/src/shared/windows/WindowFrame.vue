<script setup lang="ts">
import { ref } from "vue"

import { AppIconButton } from "@/shared/ui"

import type { WindowState } from "./useWindows"

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
}>()

const dragging = ref(false)
let grabbedAt = { x: 0, y: 0 }

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
</script>

<template>
  <section
    class="app-window"
    :class="{ 'app-window--front': front }"
    :style="{
      left: `${window.rect.x}px`,
      top: `${window.rect.y}px`,
      width: `${window.rect.width}px`,
      height: `${window.rect.height}px`,
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

    <div class="app-window__body">
      <component :is="window.component" />
    </div>
  </section>
</template>

<style scoped>
.app-window {
  position: fixed;
  /* Above the application's own chrome — Quasar puts a header and a footer at
     2000 — and above a sticky table heading, which declares 1 and would
     otherwise paint over a window that declared nothing at all. Below q-menu
     and q-dialog at 6000: a select, an action menu and the confirmation of a
     close all open *from* a window and have to land on top of it.
     Order within this layer is the order of the array, not a counter. */
  z-index: 3000;
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
</style>
