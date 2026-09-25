<script setup lang="ts">
import { WorkspacePanelTarget } from "@/shared/workspace"

import PairBar from "./PairBar.vue"
import type { Pair } from "./pairs"

/**
 * The body of a pair window: the two catalog panels, alive, and the bar of
 * what can be done between them (D167). Minimized, the panels park and keep
 * what they hold, as a detached one does (D93).
 */
defineProps<{ pair: Pair; windowId: string; minimized: boolean }>()
</script>

<template>
  <div
    class="pair-window"
    data-testid="pair-window"
  >
    <div class="pair-window__sides">
      <div
        class="pair-window__side"
        data-testid="pair-side-left"
      >
        <WorkspacePanelTarget
          :target-id="`${windowId}:left`"
          :panel-id="minimized ? null : pair.left.panelId"
        />
      </div>
      <div class="pair-window__rule" />
      <div
        class="pair-window__side"
        data-testid="pair-side-right"
      >
        <WorkspacePanelTarget
          :target-id="`${windowId}:right`"
          :panel-id="minimized ? null : pair.right.panelId"
        />
      </div>
    </div>
    <PairBar
      :left="pair.left"
      :right="pair.right"
    />
  </div>
</template>

<style scoped>
.pair-window {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
}
.pair-window__sides {
  display: flex;
  flex: 1;
  min-height: 0;
}
.pair-window__side {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
}
.pair-window__rule {
  width: 1px;
  background: var(--dp-border);
}
</style>
