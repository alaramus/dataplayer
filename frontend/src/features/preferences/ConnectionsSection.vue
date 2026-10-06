<script setup lang="ts">
import { computed } from "vue"

import { usePreferences, useUpdatePreferences } from "@/features/preferences/api"
import { checkIntervalOptions } from "@/features/preferences/checks"
import type { CheckInterval } from "@/features/preferences/checks"
import { messageOf } from "@/shared/api/errors"
import { AppForm, AppSelect, AppSpinner, useToast } from "@/shared/ui"

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

  <div
    v-else
    class="preferences-section"
  >
    <section class="preferences__row">
      <div class="preferences__what">
        <span class="preferences__title">Check that connections are reachable</span>
        <span class="preferences__summary">
          Every connection is probed on this schedule while a workspace is open, and
          the dot beside it says what the last answer was. A probe opens a connection
          of its own, so a slow or distant server is worth asking less often.
        </span>
      </div>
      <AppForm
        class="preferences__control-form"
        layout="section"
      >
        <AppSelect
          class="preferences__control"
          :model-value="chosen"
          :options="intervals"
          :loading="save.isPending.value"
          aria-label="How often connections are checked"
          data-testid="preference-connector-checks"
          @update:model-value="chooseInterval"
        />
      </AppForm>
    </section>
  </div>
</template>

<style scoped>
.preferences-section {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}
.preferences__waiting {
  display: flex;
  justify-content: center;
  padding: var(--dp-space-5);
}
/* The same question-and-answer rows GeneralSection draws: one grid beside
   the sections list, two bodies showing it. Copied rather than shared so
   neither section depends on the other's file. */
.preferences__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  gap: var(--dp-space-5);
  align-items: start;
  padding: var(--dp-space-4) 0;
  border-bottom: 1px solid var(--dp-border);
}
.preferences__control-form {
  padding: 0;
}
.preferences__what {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
}
.preferences__title {
  font-weight: 500;
}
.preferences__summary {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
}
/* Narrow: the control goes under the question it answers. */
@media (max-width: 700px) {
  .preferences__row {
    grid-template-columns: 1fr;
  }
}
</style>
