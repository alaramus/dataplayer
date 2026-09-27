<script setup lang="ts">
import { computed } from "vue"

import { useServices } from "@/features/services/api"
import { isWorking, progressOf } from "@/features/services/jobs"
import { isRunning } from "@/features/services/lifecycle"
import { servicesCommand } from "@/features/workspace/commands"
import { useBottomPanel } from "@/features/workspace/useBottomPanel"
import { AppBadge, AppButton, AppTooltip } from "@/shared/ui"

/**
 * What this server is running for this person: the switch of the Services
 * tool in the panel at the foot of the workspace (D143). It is about the
 * machine rather than about the open connection, so it stands apart from the
 * commands.
 *
 * While a job is working the button says the step it has reached: once the
 * dialog that asked for a service has closed, this is the only place a start
 * is visible (D81).
 */
const services = useServices()
const working = computed(() => {
  const busy = (services.data.value ?? []).find((row) => isWorking(row.job))
  return busy === undefined ? null : `${busy.connector_name}: ${progressOf(busy.job)}`
})
/**
 * How many run now, on the button: a database left running uses the machine
 * whether or not anybody is looking at it, as a terminal left open does.
 */
const running = computed(() => (services.data.value ?? []).filter(isRunning).length)
const command = computed(() =>
  servicesCommand({
    count: (services.data.value ?? []).length,
    running: running.value,
    working: working.value,
  })
)
const panel = useBottomPanel()
const shown = computed(() => panel.open.value === "services")

/** Icon-only rendering for the side tool rails. */
withDefaults(defineProps<{ iconOnly?: boolean }>(), { iconOnly: false })
</script>

<template>
  <!-- The tooltip hangs off this rather than off the button: a disabled Quasar
       button takes no pointer events, and the reason it is disabled is the one
       thing worth reading there. -->
  <span class="services-command">
    <!-- Pressed while its tool is the one shown, as a space is in the
         switch beside it. -->
    <AppButton
      :variant="shown ? 'chosen' : 'quiet'"
      size="sm"
      :icon="command.icon"
      :label="command.label"
      :icon-only="iconOnly"
      :disable="!command.enabled"
      :aria-pressed="shown"
      data-testid="command-services"
      @click="panel.toggle('services')"
    >
      <AppBadge
        v-if="running > 0"
        corner
        :label="String(running)"
        data-testid="services-count"
      />
    </AppButton>
    <AppTooltip>{{ command.tooltip }}</AppTooltip>
  </span>
</template>

<style scoped>
.services-command {
  display: flex;
  align-items: center;
}
</style>
