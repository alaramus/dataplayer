<script setup lang="ts">
import { provide } from "vue"

import WindowFrame from "./WindowFrame.vue"
import { windowsKey } from "./useWindows"
import type { WindowsContext } from "./useWindows"

/**
 * Every open window, stacked back to front.
 *
 * Order in the array is the stacking order, so no element carries a z-index
 * of its own and there is no counter to grow without bound.
 */
const props = defineProps<{ context: WindowsContext }>()

provide(windowsKey, props.context)

async function requestClose(id: string) {
  const ask = props.context.confirmClose
  if (ask !== null && !(await ask(id))) return
  props.context.close(id)
}
</script>

<template>
  <WindowFrame
    v-for="entry in context.windows.value"
    :key="entry.key"
    :window="entry"
    :front="entry.id === context.frontId.value"
    @focus="context.focus(entry.id)"
    @close="requestClose(entry.id)"
    @move="context.move(entry.id, $event)"
  />
</template>
