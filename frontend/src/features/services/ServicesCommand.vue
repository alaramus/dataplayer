<script setup lang="ts">
import { computed } from "vue"

import { useServices } from "@/features/services/api"
import { isWorking, progressOf } from "@/features/services/jobs"
import { servicesCommand } from "@/features/workspace/commands"
import { useBottomPanel } from "@/features/workspace/useBottomPanel"
import { AppButton, AppTooltip } from "@/shared/ui"

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
const command = computed(() =>
  servicesCommand({ count: (services.data.value ?? []).length, working: working.value })
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
      :variant="shown ? 'secondary' : 'quiet'"
      size="sm"
      :icon="command.icon"
      :label="iconOnly ? undefined : command.label"
      :disable="!command.enabled"
      :aria-pressed="shown"
      data-testid="command-services"
      @click="panel.toggle('services')"
    />
    <AppTooltip>{{ command.tooltip }}</AppTooltip>
  </span>
</template>

<style scoped>
.services-command {
  display: flex;
  align-items: center;
}
</style>
