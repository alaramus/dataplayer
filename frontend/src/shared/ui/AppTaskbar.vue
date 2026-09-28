<script setup lang="ts">
/**
 * The row of things that are open and not in front of you, at the foot of the
 * screen: windows, and sections of the workspace put aside.
 *
 * A component rather than a class each bar copies, because the one thing that
 * is easy to get wrong here is the same in both: the bar must never change the
 * height of the line it sits in. It did — a scrollbar appeared under a row of
 * nine windows and pushed the whole footer fifteen pixels taller, so opening a
 * window moved the bottom of every column on the screen.
 */
import { ref } from "vue"

defineProps<{ label: string }>()

/**
 * The row itself, for a bar that has to find something inside it — the window
 * manager puts focus on the button of a window that has just been put aside,
 * because that button is the only thing left on screen leading back to it.
 */
const row = ref<HTMLElement | null>(null)
defineExpose({ row })
</script>

<template>
  <nav
    ref="row"
    class="taskbar"
    :aria-label="label"
  >
    <slot />
  </nav>
</template>

<style scoped>
.taskbar {
  display: flex;
  align-items: center;
  align-self: center;
  gap: var(--dp-space-1);
  min-width: 0;
  max-height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  font-size: var(--dp-font-size-sm);
  /* No bar of its own: it would be thicker than the line it sits in, and it
     takes that thickness out of the footer. What does not fit is reached by
     the wheel, the way the catalog's trail of crumbs is. */
  scrollbar-width: none;
}
.taskbar::-webkit-scrollbar {
  display: none;
}
</style>
