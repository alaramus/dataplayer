<script setup lang="ts">
import type { WorkspaceContext } from "./context"

defineProps<{
  context: WorkspaceContext
  panelId: string
  target: HTMLElement | null
  parking: HTMLElement
}>()
</script>

<template>
  <Teleport :to="target ?? parking">
    <div class="workspace-panel">
      <!-- The cache belongs to the panel, so changing its DOM destination
           never disposes an editor, its draft or a transaction it owns. -->
      <KeepAlive>
        <component
          :is="context.componentOf(panelId)"
          v-if="target !== null"
          :key="context.keyOf(panelId)"
        />
      </KeepAlive>
    </div>
  </Teleport>
</template>

<style scoped>
.workspace-panel {
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
</style>
