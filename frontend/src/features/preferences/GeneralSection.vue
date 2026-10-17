<script setup lang="ts">
import { ref } from "vue"

import OnboardingDialog from "@/features/onboarding/OnboardingDialog.vue"
import { useLanguageChoice } from "@/features/preferences/languageChoice"
import VoiceSelect from "@/features/speech/VoiceSelect.vue"
import { speechSupported } from "@/features/speech/voices"
import { t } from "@/shared/i18n"
import { AppButton, AppForm, AppSelect, AppSettingRow } from "@/shared/ui"
import { THEME_CHOICES, useThemeStore } from "@/stores/theme"
import type { ThemeMode } from "@/stores/theme"

// What this account chose for itself, and what this browser holds for it.
// The language and the theme are the account's, so they follow the person to
// any browser (D224); AccountPreferences keeps the theme on the account.
// The voice reading aloud is this browser's: voices are the browser's own.
// Nowhere to choose it where there is nothing to synthesise.
const theme = useThemeStore()
const speechOk = speechSupported()

// The welcome tour, on demand: finished or skipped long ago, it opens here
// again from its first clip rather than from the theme choice above.
const tourOpen = ref(false)

const language = useLanguageChoice()
</script>

<template>
  <div class="preferences-section">
    <AppSettingRow
      :title="t('language.label')"
      :summary="t('preferences.language_summary')"
    >
      <AppForm>
        <AppSelect
          :model-value="language.chosen.value"
          :options="language.options.value"
          :loading="language.saving.value"
          :aria-label="t('language.label')"
          data-testid="preference-language"
          @update:model-value="language.choose"
        />
      </AppForm>
    </AppSettingRow>
    <AppSettingRow
      :title="t('preferences.appearance')"
      :summary="t('preferences.appearance_summary')"
    >
      <AppForm>
        <AppSelect
          :model-value="theme.mode"
          :options="THEME_CHOICES"
          :aria-label="t('theme.label')"
          data-testid="preference-theme"
          @update:model-value="theme.set($event as ThemeMode)"
        />
      </AppForm>
    </AppSettingRow>
    <AppSettingRow
      v-if="speechOk"
      :title="t('preferences.voice')"
      :summary="t('preferences.voice_summary')"
    >
      <AppForm>
        <VoiceSelect
          :aria-label="t('preferences.voice')"
          data-testid="preference-voice"
        />
      </AppForm>
    </AppSettingRow>
    <AppSettingRow
      :title="t('preferences.tour')"
      :summary="t('preferences.tour_summary')"
    >
      <AppButton
        :label="t('preferences.replay_tour')"
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
