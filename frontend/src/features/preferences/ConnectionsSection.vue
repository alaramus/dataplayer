<script setup lang="ts">
import { computed } from "vue"

import { usePreferences, useUpdatePreferences } from "@/features/preferences/api"
import { checkIntervalOptions } from "@/features/preferences/checks"
import type { CheckInterval } from "@/features/preferences/checks"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
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

const intervals = computed(() => checkIntervalOptions())
// Whatever the server says it is, and nothing while it has not said: a
// default written here too would be a second place for it to be wrong.
const chosen = computed(() => preferences.data.value?.connector_checks)

async function chooseInterval(value: unknown) {
  const connector_checks = value as CheckInterval
  if (connector_checks === chosen.value) return
  try {
    await save.mutateAsync({ connector_checks })
    toast.success(t("preferences.saved"))
  } catch (cause) {
    toast.error(messageOf(cause, t("preferences.not_saved")))
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
    :title="t('preferences.checks')"
    :summary="t('preferences.checks_summary')"
  >
    <AppForm>
      <AppSelect
        :model-value="chosen"
        :options="intervals"
        :loading="save.isPending.value"
        :aria-label="t('preferences.checks_label')"
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
