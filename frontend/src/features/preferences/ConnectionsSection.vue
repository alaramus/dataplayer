<script setup lang="ts">
import { computed } from "vue"

import { usePreferences, useUpdatePreferences } from "@/features/preferences/api"
import { checkIntervalOptions } from "@/features/preferences/checks"
import type { CheckInterval } from "@/features/preferences/checks"
import { messageOf } from "@/shared/api/errors"
import { AppForm, AppSelect, AppSettingRow, AppSpinner, useToast } from "@/shared/ui"

/**
 * How often this account asks after its connections.
 *
 * Saved as it is changed. There is no draft to lose and nothing to validate
 * against anything else, so a Save button would be a second gesture asking
 * the same question the menu already asked.
 */
const toast = useToast()
const preferences = usePreferences()
const save = useUpdatePreferences()

const intervals = checkIntervalOptions()
// Whatever the server says it is, and nothing while it has not said: a
// default written here too would be a second place for it to be wrong.
const chosen = computed(() => preferences.data.value?.connector_checks)

async function chooseInterval(value: unknown) {
  const connector_checks = value as CheckInterval
  if (connector_checks === chosen.value) return
  try {
    await save.mutateAsync({ connector_checks })
    toast.success("Preference saved")
  } catch (cause) {
    toast.error(messageOf(cause, "The preference could not be saved"))
  }
}
</script>

<template>
  <div
    v-if="preferences.isLoading.value"
    class="preferences__waiting"
  >
    <AppSpinner />
  </div>

  <AppSettingRow
    v-else
    title="Check that connections are reachable"
    summary="Every connection is probed on this schedule while a workspace is open, and the dot beside it says what the last answer was. A probe opens a connection of its own, so a slow or distant server is worth asking less often."
  >
    <AppForm>
      <AppSelect
        :model-value="chosen"
        :options="intervals"
        :loading="save.isPending.value"
        aria-label="How often connections are checked"
        data-testid="preference-connector-checks"
        @update:model-value="chooseInterval"
      />
    </AppForm>
  </AppSettingRow>
</template>

<style scoped>
.preferences__waiting {
  display: flex;
  justify-content: center;
  padding: var(--dp-space-5);
}
</style>
