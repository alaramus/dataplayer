<script setup lang="ts">
import { ref } from "vue"

import OnboardingDialog from "@/features/onboarding/OnboardingDialog.vue"
import VoiceSelect from "@/features/speech/VoiceSelect.vue"
import { speechSupported } from "@/features/speech/voices"
import { AppButton, AppForm, AppSelect } from "@/shared/ui"
import type { SelectOption } from "@/shared/ui"
import { THEMES, useThemeStore } from "@/stores/theme"
import type { ThemeMode } from "@/stores/theme"

// What this account chose for itself, and what this browser holds for it.
// The theme lives here, next to the account, rather than in the header. Kept
// in this browser rather than on the server (D6), so it is not saved anywhere.
// The voice reading aloud lives here for the same reason: voices are this
// browser's own. Nowhere to choose it where there is nothing to synthesise.
const theme = useThemeStore()
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
</script>

<template>
  <div class="preferences-section">
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
  </div>
  <OnboardingDialog
    v-model="tourOpen"
    start-phase="tour"
  />
</template>

<style scoped>
.preferences-section {
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
