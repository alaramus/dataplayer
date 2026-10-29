<script setup lang="ts">
import { computed } from "vue"

import { t } from "@/shared/i18n"
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

// Pipelines beside Data: both stand on the same list of connections, so the
// switch between them keeps that card where it was.
const choices = computed<{ value: Space; label: string; icon: string; tooltip: string }[]>(() => [
  { value: "data", label: t("dashboards.switch.data"), icon: appIcons.tableChart, tooltip: t("dashboards.switch.data_hint") },
  {
    value: "pipelines",
    label: t("dashboards.switch.pipelines"),
    icon: appIcons.accountTree,
    tooltip: t("dashboards.switch.pipelines_hint"),
  },
  {
    value: "dashboards",
    label: t("dashboards.switch.dashboards"),
    icon: appIcons.dashboard,
    tooltip: t("dashboards.switch.dashboards_hint"),
  },
  { value: "ai", label: t("dashboards.switch.ai"), icon: appIcons.robot2, tooltip: t("dashboards.switch.ai_hint") },
])
</script>

<template>
  <div
    class="space-switch"
    role="group"
    :aria-label="t('dashboards.switch.label')"
  >
    <span
      v-for="choice in choices"
      :key="choice.value"
      class="space-switch__slot"
    >
      <AppButton
        :variant="space.current === choice.value ? 'chosen' : 'quiet'"
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
  padding-inline-end: var(--dp-space-2);
  border-inline-end: 1px solid var(--dp-separator);
}

.space-switch__slot {
  display: flex;
  align-items: center;
}
</style>
