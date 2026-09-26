<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { AppButton, AppTooltip } from "@/shared/ui"
import { useSpaceStore } from "@/stores/space"
import type { Space } from "@/stores/space"

/**
 * Data, Dashboards, AI or Pipelines (D125, D141, D175). Separate
 * buttons rather than one that changes its word: the way back is where the way
 * there was.
 */
const space = useSpaceStore()

/** Icon-only rendering for the side tool rails. */
withDefaults(defineProps<{ iconOnly?: boolean }>(), { iconOnly: false })

const choices: { value: Space; label: string; icon: string; tooltip: string }[] = [
  { value: "data", label: "Data", icon: appIcons.tableChart, tooltip: "Connections, catalogs and the work opened from them" },
  { value: "dashboards", label: "Dashboards", icon: appIcons.dashboard, tooltip: "Metrics your agents report, drawn over time" },
  { value: "ai", label: "AI", icon: appIcons.robot2, tooltip: "Conversations with the application agent" },
  { value: "pipelines", label: "Pipelines", icon: appIcons.accountTree, tooltip: "What your connections give each other, laid out and run" },
]
</script>

<template>
  <div
    class="space-switch"
    role="group"
    aria-label="Space"
  >
    <span
      v-for="choice in choices"
      :key="choice.value"
      class="space-switch__slot"
    >
      <AppButton
        :variant="space.current === choice.value ? 'secondary' : 'quiet'"
        size="sm"
        :icon="choice.icon"
        :label="choice.label"
        :icon-only="iconOnly"
        :aria-pressed="space.current === choice.value"
        :data-testid="`space-${choice.value}`"
        @click="space.show(choice.value)"
      />
      <AppTooltip>{{ choice.tooltip }}</AppTooltip>
    </span>
  </div>
</template>

<style scoped>
.space-switch {
  display: flex;
  align-items: center;
  flex: none;
  padding-right: var(--dp-space-2);
  border-right: 1px solid var(--dp-separator);
}

.space-switch__slot {
  display: flex;
  align-items: center;
}
</style>
