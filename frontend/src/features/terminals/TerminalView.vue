<script setup lang="ts">
import "@xterm/xterm/css/xterm.css"

import { nextTick, onBeforeUnmount, onMounted, useTemplateRef, watch } from "vue"

import { useThemeStore } from "@/stores/theme"

import { paintScreen } from "./screenTheme"
import type { TerminalSession } from "./useTerminals"

/**
 * One terminal's screen, lent an element while it is shown (D149).
 *
 * The screen outlives this component: it is moved in on mount and out on
 * unmount rather than made again, which is what xterm allows and what keeps
 * the scrollback when the panel shows another tool.
 */
const props = defineProps<{ session: TerminalSession }>()
const host = useTemplateRef<HTMLElement>("host")
const theme = useThemeStore()
let observer: ResizeObserver | null = null
let pending = 0

function paint() {
  if (host.value) paintScreen(props.session.screen, host.value)
}

// One fit a frame: a panel being dragged taller reports every pixel, and each
// fit that changes the size is a frame sent to the server.
function fitSoon() {
  if (pending !== 0) return
  pending = requestAnimationFrame(() => {
    pending = 0
    props.session.fit.fit()
  })
}

onMounted(() => {
  const element = host.value
  if (element === null) return
  const screen = props.session.screen
  if (screen.element === undefined) screen.open(element)
  else element.appendChild(screen.element)
  paint()
  props.session.fit.fit()
  screen.refresh(0, screen.rows - 1)
  screen.focus()
  observer = new ResizeObserver(fitSoon)
  observer.observe(element)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  cancelAnimationFrame(pending)
  pending = 0
  const element = props.session.screen.element
  if (element !== undefined && element.parentElement === host.value) element.remove()
})

watch(
  () => theme.dark,
  async () => {
    // The tokens change with a class on the body, which is put there after
    // the store has changed.
    await nextTick()
    paint()
  }
)
</script>

<template>
  <!-- Every key is the shell's (D148): the application's shortcuts let it
       alone, and Ctrl+K is readline's kill-line here. -->
  <div
    ref="host"
    class="terminal-view"
    data-testid="terminal-screen"
    data-owns-keys
  />
</template>

<style scoped>
.terminal-view {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--dp-surface);
}
/* xterm 6 draws its own scrollbar out of elements, VS Code's, so the native
   one every other surface shares (D187) never reaches it. Its width and
   position are inline styles, hence the !important; its colours cannot go
   through the xterm theme, which does not parse the color-mix() the tokens
   are made of. */
.terminal-view :deep(.xterm-scrollable-element > .scrollbar.vertical) {
  width: var(--dp-scrollbar-size) !important;
}
.terminal-view :deep(.xterm-scrollable-element > .scrollbar.vertical > .slider) {
  left: 0 !important;
  width: 100% !important;
  border-radius: var(--dp-radius-control);
  background: var(--dp-scrollbar-thumb) !important;
}
.terminal-view :deep(.xterm-scrollable-element > .scrollbar.vertical > .slider:hover),
.terminal-view :deep(.xterm-scrollable-element > .scrollbar.vertical > .slider.active) {
  background: var(--dp-scrollbar-thumb-hover) !important;
}
</style>
