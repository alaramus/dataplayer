<script setup lang="ts">
import { computed } from "vue"

import { useBottomPanel } from "@/features/workspace/useBottomPanel"
import { AppButton, AppTooltip, appIcons } from "@/shared/ui"

/**
 * The switch of the server's log in the panel at the foot of the workspace
 * (D143, D184), beside Services, Terminals and Queries. The rail draws it for
 * a superuser only (`superuserOnly` in toolBlocks.ts).
 */
withDefaults(defineProps<{ iconOnly?: boolean }>(), { iconOnly: false })

const panel = useBottomPanel()
const shown = computed(() => panel.open.value === "logs")
</script>

<template>
  <!-- The tooltip hangs off this rather than off the button, as the other
       commands on the rails do. -->
  <span class="logs-command">
    <AppButton
      :variant="shown ? 'chosen' : 'quiet'"
      size="sm"
      :icon="appIcons.receiptLong"
      label="Logs"
      :icon-only="iconOnly"
      :aria-pressed="shown"
      data-testid="command-logs"
      @click="panel.toggle('logs')"
    />
    <AppTooltip>The server's log</AppTooltip>
  </span>
</template>

<style scoped>
.logs-command {
  display: flex;
  align-items: center;
}
</style>
