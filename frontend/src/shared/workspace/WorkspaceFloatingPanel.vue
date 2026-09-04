<script setup lang="ts">
import { computed, ref } from "vue"

import { AppButton, AppIconButton } from "@/shared/ui"

import type { WorkspaceContext } from "./context"
import WorkspacePanelTarget from "./WorkspacePanelTarget.vue"

const props = defineProps<{
  context: WorkspaceContext
  panelId: string
  targetId: string
  minimized: boolean
}>()
const look = computed(() => props.context.lookOf(props.panelId))
const reloading = ref(false)

async function reload() {
  if (reloading.value) return
  reloading.value = true
  try {
    await props.context.onReload?.(props.panelId)
  } finally {
    reloading.value = false
  }
}
</script>

<template>
  <div class="floating-panel">
    <div class="floating-panel__toolbar">
      <AppButton
        variant="quiet"
        size="sm"
        icon="tab"
        label="Return to panel"
        data-testid="dock-panel"
        @click="context.dock(panelId)"
      />
      <AppIconButton
        v-if="look.iconTooltip && context.onIconClick"
        :icon="look.icon"
        :tooltip="look.iconTooltip"
        :aria-label="look.iconTooltip"
        @click="context.onIconClick?.(panelId)"
      />
      <AppIconButton
        v-if="look.reloadTooltip && context.onReload"
        icon="refresh"
        :tooltip="look.reloadTooltip"
        :aria-label="look.reloadTooltip"
        :loading="reloading"
        @click="reload"
      />
    </div>
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
.floating-panel__toolbar {
  display: flex;
  align-items: center;
  flex: none;
  gap: var(--dp-space-1);
  padding: var(--dp-space-1);
  border-bottom: 1px solid var(--dp-border);
}
</style>
