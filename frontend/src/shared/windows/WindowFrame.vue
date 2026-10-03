<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

import { AppIconButton } from "@/shared/ui"
import { panelColorStyle } from "@/shared/ui/panelColor"

import { FIT_MARGIN } from "./geometry"

import type { WindowState } from "./useWindows"
import type { ResizeEdge } from "./geometry"

/**
 * The chrome of one floating window, including its size and visibility controls.
 *
 * Dragging is pointer events rather than a directive: a pointer capture keeps
 * the window following the cursor when it leaves the bar, which is what makes
 * a fast drag not lose the window halfway.
 */
const props = defineProps<{ window: WindowState; front: boolean; bottomInset: number }>()

const emit = defineEmits<{
  focus: []
  minimize: []
  toggleMaximize: []
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
  if (event.button !== 0 || props.window.maximized) return
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
  if (
    props.window.autoFit === false || props.window.minimized || props.window.maximized ||
    frame.value === null || body.value === null
  ) return
  const bar = frame.value.querySelector<HTMLElement>(".app-window__bar")
  emit("fit", {
    width: Math.ceil(Math.max(props.window.rect.width, body.value.scrollWidth + 2)),
    height: Math.ceil((bar?.offsetHeight ?? 0) + body.value.scrollHeight + 2),
  })
}

/**
 * The keys handed to the window, which is not a place Tab lands on.
 *
 * Trap: a browser draws a focus ring on a script's focus when the focus it
 * moves from was drawn with one, and a text field always is. A window opened
 * from the search's field was ringed whole until a press inside it.
 */
function holdKeys() {
  frame.value?.focus({ preventScroll: true, focusVisible: false })
}

onMounted(async () => {
  await nextTick()
  // A form may already have focused one of its fields while mounting.
  if (props.front && !props.window.minimized && !frame.value?.contains(document.activeElement)) {
    holdKeys()
  }
  window.requestAnimationFrame(measure)
  if (typeof ResizeObserver !== "undefined" && body.value !== null) {
    observer = new ResizeObserver(measure)
    observer.observe(body.value)
    if (body.value.firstElementChild) observer.observe(body.value.firstElementChild)
  }
})

onBeforeUnmount(() => observer?.disconnect())

watch(
  () => props.window.minimized,
  async (minimized) => {
    if (minimized) return
    await nextTick()
    holdKeys()
    measure()
  }
)

function startResize(edge: ResizeEdge, event: PointerEvent) {
  if (event.button !== 0 || props.window.maximized) return
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

/**
 * Escape asks a question to close, exactly as its cross does (U12).
 *
 * Only a window that says it is dismissible, which is a question and not a
 * form - workspace.md says why. Asks rather than closes, so the answer path is
 * the one the cross already takes. Only the window in front, and only where
 * nothing inside has already dealt with the key: a menu or a select over the
 * window is teleported out of it and answers Escape itself, but anything that
 * handles the key here and says so keeps it.
 */
function dismiss(event: KeyboardEvent) {
  if (!props.front || props.window.dismissible !== true || event.defaultPrevented) return
  emit("close")
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
  <!-- An automatically fitted window keeps measuring for its whole lifetime.
       A manual resize turns autoFit off and restores a fixed height. -->
  <section
    v-show="!window.minimized"
    ref="frame"
    class="app-window"
    :class="{ 'app-window--front': front, 'app-window--maximized': window.maximized }"
    :style="{
      left: window.maximized ? '0' : `${window.rect.x}px`,
      top: window.maximized ? '0' : `${window.rect.y}px`,
      width: window.maximized ? '100vw' : `${window.rect.width}px`,
      height: window.maximized
        ? `calc(100dvh - ${bottomInset}px)`
        : window.autoFit !== false ? 'auto' : `${window.rect.height}px`,
      maxHeight:
        !window.maximized && window.autoFit !== false ? `calc(100vh - ${FIT_MARGIN}px)` : undefined,
    }"
    :data-testid="`window-${window.id}`"
    role="dialog"
    tabindex="-1"
    :aria-label="window.look.title"
    @pointerdown="emit('focus')"
    @keydown.esc="dismiss"
  >
    <header
      class="app-window__bar"
      :style="panelColorStyle(window.look.color)"
      :data-testid="`window-bar-${window.id}`"
      @pointerdown="startDrag"
      @pointermove="onDrag"
      @pointerup="endDrag"
      @pointercancel="endDrag"
      @dblclick="emit('toggleMaximize')"
    >
      <q-icon
        v-if="window.look.icon"
        :name="window.look.icon"
        size="var(--dp-icon-sm)"
      />
      <span class="app-window__title">{{ window.look.title }}</span>
      <!-- Wrapped so the drag handler above does not see the press. -->
      <span
        class="app-window__controls"
        @pointerdown.stop
        @dblclick.stop
      >
        <!-- What this window can do about itself, before what every window
             can do about itself. A detached panel's way back is here rather
             than in the panel's own row of commands: it is about the frame,
             the way minimize and close are, and not about what is inside it
             (D112). -->
        <AppIconButton
          v-for="action in window.actions ?? []"
          :key="action.icon"
          :icon="action.icon"
          :tooltip="action.tooltip"
          :aria-label="action.tooltip"
          :data-testid="action.testid"
          @click="action.run()"
        />
        <!-- The dash a workspace section is put aside with, drawn on the line
             of its neighbours: Material's "minimize" sits on the baseline,
             under the square and the cross beside it (D187). -->
        <AppIconButton
          :icon="appIcons.remove"
          tooltip="Minimize"
          aria-label="Minimize"
          :data-testid="`window-minimize-${window.id}`"
          @click="emit('minimize')"
        />
        <AppIconButton
          :icon="window.maximized ? appIcons.filterNone : appIcons.cropSquare"
          :tooltip="window.maximized ? 'Restore size' : 'Maximize'"
          :aria-label="window.maximized ? 'Restore size' : 'Maximize'"
          :data-testid="`window-maximize-${window.id}`"
          @click="emit('toggleMaximize')"
        />
        <AppIconButton
          class="dp-window-close"
          :icon="appIcons.close"
          tooltip="Close"
          variant="danger-quiet"
          aria-label="Close window"
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
      v-for="edge in window.maximized ? [] : resizeEdges"
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
  /* A panel's border, so a window reads as the same kind of card. The one in
     front is told by its shadow: a bright border of its own looked thicker
     than every panel's. */
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  box-shadow: 0 6px 24px var(--dp-shadow);
  /* The frame itself clips nothing: the resize handles below hang outside
     it, where clipping would cut them off. The bar and the body round their
     own outer corners instead, so content still meets a round frame. */
}
.app-window--front {
  box-shadow: 0 10px 40px var(--dp-shadow-strong);
}
.app-window--maximized {
  border-radius: 0;
}
.app-window--maximized .app-window__bar,
.app-window--maximized .app-window__body {
  border-radius: 0;
}
.app-window--maximized .app-window__bar {
  cursor: default;
}
.app-window__controls {
  display: flex;
  flex: none;
}
/* The height and inset of a column's head, so a window reads as the same kind
   of card: grown around its 32px buttons by padding, it stood 8px taller than
   every head of the workspace behind it. */
.app-window__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  box-sizing: border-box;
  height: var(--dp-tab-strip-height);
  padding: 0 var(--dp-space-1) 0 var(--dp-space-2);
  background: var(--dp-panel-background, var(--dp-chrome));
  color: var(--dp-panel-foreground, inherit);
  /* Otherwise a drag selects the title text instead of moving the window. */
  user-select: none;
  touch-action: none;
  border-radius: var(--dp-radius-panel) var(--dp-radius-panel) 0 0;
  /* The close control's hover block is square and reaches the bar's edge by
     its own shadow: the bar's round corner trims it, as the frame's did
     before the resize handles moved outside it. Tooltips hang off teleported
     content and are not clipped by this. */
  overflow: hidden;
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
  overflow: hidden;
  border-radius: 0 0 var(--dp-radius-panel) var(--dp-radius-panel);
}
.app-window__resize {
  position: absolute;
  touch-action: none;
}
/* The grab zone hangs outside the frame, the way an operating system's
   does: nothing inside the window resizes, so a scrollbar at the content's
   edge keeps the press. */
.app-window__resize--top,
.app-window__resize--bottom {
  left: 0;
  right: 0;
  height: 8px;
  cursor: ns-resize;
}
.app-window__resize--top { top: -8px; }
.app-window__resize--bottom { bottom: -8px; }
.app-window__resize--left,
.app-window__resize--right {
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: ew-resize;
}
.app-window__resize--left { left: -8px; }
.app-window__resize--right { right: -8px; }
.app-window__resize--top-left,
.app-window__resize--top-right,
.app-window__resize--bottom-left,
.app-window__resize--bottom-right {
  width: 12px;
  height: 12px;
}
.app-window__resize--top-left { top: -12px; left: -12px; cursor: nwse-resize; }
.app-window__resize--top-right { top: -12px; right: -12px; cursor: nesw-resize; }
.app-window__resize--bottom-left { bottom: -12px; left: -12px; cursor: nesw-resize; }
.app-window__resize--bottom-right { bottom: -12px; right: -12px; cursor: nwse-resize; }
</style>
