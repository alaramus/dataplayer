<script setup lang="ts">
import { ref } from "vue"

import OnboardingDialog from "@/features/onboarding/OnboardingDialog.vue"
import VoiceSelect from "@/features/speech/VoiceSelect.vue"
import { speechSupported } from "@/features/speech/voices"
import { AppButton, AppForm, AppSelect, AppSettingRow } from "@/shared/ui"
import { THEME_CHOICES, useThemeStore } from "@/stores/theme"
import type { ThemeMode } from "@/stores/theme"

// What this account chose for itself, and what this browser holds for it.
// The theme lives here, next to the account, rather than in the header. Kept
// in this browser rather than on the server (D6).
// The voice reading aloud lives here for the same reason: voices are this
// browser's own. Nowhere to choose it where there is nothing to synthesise.
const theme = useThemeStore()
const speechOk = speechSupported()

// The welcome tour, on demand: finished or skipped long ago, it opens here
// again from its first clip rather than from the theme choice above.
const tourOpen = ref(false)
</script>

<template>
  <div class="preferences-section">
    <AppSettingRow
      title="Appearance"
      summary="A light or dark theme for the whole application, or Light and Dark as the operating system switches between them. Kept in this browser."
    >
      <AppForm>
        <AppSelect
          :model-value="theme.mode"
          :options="THEME_CHOICES"
          aria-label="Theme"
          data-testid="preference-theme"
          @update:model-value="theme.set($event as ThemeMode)"
        />
      </AppForm>
    </AppSettingRow>
    <AppSettingRow
      v-if="speechOk"
      title="Reading voice"
      summary="The voice reading messages aloud, anywhere they are read. Voices are this browser's own. Kept in this browser."
    >
      <AppForm>
        <VoiceSelect
          aria-label="Reading voice"
          data-testid="preference-voice"
        />
      </AppForm>
    </AppSettingRow>
    <AppSettingRow
      title="Welcome tour"
      summary="The short clips from the first visit, one for each main part of the application. Opens here again whenever it is wanted."
    >
      <AppButton
        label="Replay tour"
        data-testid="preference-replay-tour"
        @click="tourOpen = true"
      />
    </AppSettingRow>
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
</style>
