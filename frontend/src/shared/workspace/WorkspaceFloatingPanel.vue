<script setup lang="ts">
import WorkspacePanelTarget from "./WorkspacePanelTarget.vue"

/**
 * The body of a window a panel was torn off into.
 *
 * Nothing but the panel. There used to be a strip of commands above it —
 * the way back, the panel's icon and a reload — and it was a second row of
 * buttons over a panel that already draws one. All three moved into that row,
 * where a detached panel offers the way back beside everything else it offers
 * (D112).
 */
defineProps<{ panelId: string; targetId: string; minimized: boolean }>()
</script>

<template>
  <div class="floating-panel">
    <WorkspacePanelTarget
      :target-id="targetId"
      :panel-id="minimized ? null : panelId"
    />
  </div>
</template>

<style scoped>
.floating-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  min-width: 0;
}
</style>
