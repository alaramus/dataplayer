<script setup lang="ts">
import { computed, ref } from "vue"
import { useRouter } from "vue-router"

import OnboardingDialog from "@/features/onboarding/OnboardingDialog.vue"
import { usePreferences, useUpdatePreferences } from "@/features/preferences/api"
import { checkIntervalOptions } from "@/features/preferences/checks"
import type { CheckInterval } from "@/features/preferences/checks"
import VoiceSelect from "@/features/speech/VoiceSelect.vue"
import { speechSupported } from "@/features/speech/voices"
import SshKeysSection from "@/features/sshKeys/SshKeysSection.vue"
import { messageOf } from "@/shared/api/errors"
import {
  AppButton,
  AppForm,
  AppLayout,
  AppPageHeader,
  AppSelect,
  AppSpinner,
  useToast,
} from "@/shared/ui"
import type { SelectOption } from "@/shared/ui"
import { THEMES, useThemeStore } from "@/stores/theme"
import type { ThemeMode } from "@/stores/theme"

/**
 * What this account chose for itself.
 *
 * One row per preference: a label, the control that answers it, and a line
 * saying what the answer costs. The next preference is another row rather
 * than a rearrangement of this screen — which is why there is no sections
 * rail here as there is under Administration: a rail for one entry is a
 * second thing to read before the only setting on the page.
 *
 * Saved as it is changed. There is no draft to lose and nothing to validate
 * against anything else, so a Save button would be a second gesture asking
 * the same question the menu already asked.
 */
const router = useRouter()
const toast = useToast()
const preferences = usePreferences()
const save = useUpdatePreferences()
// The theme lives here, next to the account, rather than in the header. Kept
// in this browser rather than on the server (D6), so it is not saved above.
const theme = useThemeStore()
// The voice reading aloud lives here for the same reason: voices are this
// browser's own. Nowhere to choose it where there is nothing to synthesise.
const speechOk = speechSupported()
const themes: SelectOption[] = [
  ...THEMES.map(({ label, value, ...theme }) =>
    "description" in theme ? { label, value, description: theme.description } : { label, value }
  ),
  { label: "System", value: "system", description: "Light or Dark, as the operating system changes" },
]

// The welcome tour, on demand: finished or skipped long ago, it opens here
// again from its first clip rather than from the theme choice above.
const tourOpen = ref(false)

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
  <AppLayout fill>
    <div
      class="app-layout__surface preferences-page"
      data-testid="preferences-page-surface"
    >
      <AppPageHeader title="Preferences">
        <template #actions>
          <AppButton
            variant="quiet"
            label="Back to workspace"
            data-testid="back-to-workspace"
            @click="router.push({ name: 'workspace' })"
          />
        </template>
      </AppPageHeader>

      <div
        v-if="preferences.isLoading.value"
        class="preferences__waiting"
      >
        <AppSpinner />
      </div>

      <div
        v-else
        class="preferences"
        data-testid="preferences"
      >
        <section class="preferences__row">
          <div class="preferences__what">
            <span class="preferences__title">Appearance</span>
            <span class="preferences__summary">
              A light or dark theme for the whole application, or Light and
              Dark as the operating system switches between them. Kept in
              this browser.
            </span>
          </div>
          <AppForm
            class="preferences__control-form"
            layout="section"
          >
            <AppSelect
              class="preferences__control"
              :model-value="theme.mode"
              :options="themes"
              aria-label="Theme"
              data-testid="preference-theme"
              @update:model-value="theme.set($event as ThemeMode)"
            />
          </AppForm>
        </section>
        <section
          v-if="speechOk"
          class="preferences__row"
        >
          <div class="preferences__what">
            <span class="preferences__title">Reading voice</span>
            <span class="preferences__summary">
              The voice reading messages aloud, anywhere they are read. Voices
              are this browser's own. Kept in this browser.
            </span>
          </div>
          <AppForm
            class="preferences__control-form"
            layout="section"
          >
            <VoiceSelect
              aria-label="Reading voice"
              data-testid="preference-voice"
            />
          </AppForm>
        </section>
        <section class="preferences__row">
          <div class="preferences__what">
            <span class="preferences__title">Welcome tour</span>
            <span class="preferences__summary">
              The six short clips from the first visit — creating a
              connection, tabs, tables, pipelines, dashboards and the AI
              agent. Opens here again whenever it is wanted.
            </span>
          </div>
          <AppForm
            class="preferences__control-form"
            layout="section"
          >
            <AppButton
              label="Replay tour"
              data-testid="preference-replay-tour"
              @click="tourOpen = true"
            />
          </AppForm>
        </section>
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
        <!-- Not a preference but the account's own: a list rather than a row,
             because a person holds several keys and each has its own commands. -->
        <SshKeysSection />
      </div>
      <OnboardingDialog
        v-model="tourOpen"
        start-phase="tour"
      />
    </div>
  </AppLayout>
</template>

<style scoped>
/* One column of reading, head included: the head ran the width of the screen
   while the settings under it stopped at 900px, and "Back to workspace" stood
   half a screen away from anything it belonged to. */
.preferences-page > * {
  max-width: var(--dp-page-max-width);
}
.preferences__waiting {
  display: flex;
  justify-content: center;
  padding: var(--dp-space-5);
}
.preferences {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}
/* The question on the left and its answer on the right, so a page of them
   reads down one column of controls rather than as a stack of forms. */
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
