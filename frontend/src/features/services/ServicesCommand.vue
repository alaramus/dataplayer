<script setup lang="ts">
import { computed, ref } from "vue"

import ServicesDialog from "@/features/services/ServicesDialog.vue"
import { useServices } from "@/features/services/api"
import { isWorking, progressOf } from "@/features/services/jobs"
import { servicesCommand } from "@/features/workspace/commands"
import { AppButton, AppTooltip } from "@/shared/ui"

/**
 * What this server is running for this person, at the far end of the status
 * bar: it is about the machine rather than about the open connection, so it
 * stands with the activity indicator and not among the commands.
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
const open = ref(false)

/** Icon-only rendering for the side tool rails. */
withDefaults(defineProps<{ iconOnly?: boolean }>(), { iconOnly: false })
</script>

<template>
  <!-- The tooltip hangs off this rather than off the button: a disabled Quasar
       button takes no pointer events, and the reason it is disabled is the one
       thing worth reading there. -->
  <span class="services-command">
    <AppButton
      variant="quiet"
      size="sm"
      :icon="command.icon"
      :label="iconOnly ? undefined : command.label"
      :disable="!command.enabled"
      data-testid="command-services"
      @click="open = true"
    />
    <AppTooltip>{{ command.tooltip }}</AppTooltip>

    <ServicesDialog v-model="open" />
  </span>
</template>

<style scoped>
.services-command {
  display: flex;
  align-items: center;
}
</style>
