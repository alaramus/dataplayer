<script setup lang="ts">
import { inject, onBeforeUnmount, ref, watch } from "vue"

import { panelTargetsKey } from "./panelTargets"

const props = defineProps<{ targetId: string; panelId: string | null }>()
const targets = inject(panelTargetsKey)
if (targets === undefined) throw new Error("A panel target needs a workspace panel host")
const registry = targets
const element = ref<HTMLElement | null>(null)

watch(
  [() => props.targetId, () => props.panelId, element],
  ([id, panelId, node], previous) => {
    if (previous[0] !== undefined && previous[0] !== id) registry.set(previous[0], null)
    registry.set(id, node === null || panelId === null ? null : { panelId, element: node })
  },
  { flush: "post" }
)
onBeforeUnmount(() => registry.set(props.targetId, null))
</script>

<template>
  <div
    ref="element"
    class="workspace-panel-target"
  >
    <slot />
  </div>
</template>

<style scoped>
.workspace-panel-target {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
</style>
