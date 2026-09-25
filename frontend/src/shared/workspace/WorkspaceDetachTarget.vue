<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { WorkspaceContext } from "./context"

const props = defineProps<{ context: WorkspaceContext }>()
const hovered = ref(false)
const offered = computed(() => props.context.dragging.value !== null &&
  props.context.canDetach(props.context.dragging.value))
watch(offered, (value) => { if (!value) hovered.value = false })

function release() {
  const panelId = props.context.dragging.value
  if (panelId !== null) props.context.detach(panelId)
  hovered.value = false
}
</script>

<template>
  <div
    v-if="offered"
    class="detach-targets"
  >
    <div
      class="detach-target"
      :class="{ 'detach-target--hovered': hovered }"
      data-testid="workspace-detach-target"
      role="status"
      @pointerenter="hovered = true"
      @pointerleave="hovered = false"
      @pointerup.stop="release"
    >
      <q-icon
        name="web_asset"
        size="28px"
      />
      <span>Drop here to open in a window</span>
    </div>
    <!-- Another place the feature offers for the same carried tab, beside
         this one rather than instead of it. -->
    <slot
      name="beside"
      :panel-id="context.dragging.value"
    />
  </div>
</template>

<style scoped>
.detach-targets {
  position: absolute;
  inset: 0;
  z-index: var(--dp-layer-overlay);
  display: flex;
  gap: var(--dp-space-2);
}
.detach-target {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--dp-space-2);
  border: 2px dashed var(--dp-dropzone-border);
  background: var(--dp-chrome-raised);
  color: var(--dp-text-strong);
}
.detach-target--hovered {
  border-style: solid;
  background: var(--dp-dropzone);
}
</style>
