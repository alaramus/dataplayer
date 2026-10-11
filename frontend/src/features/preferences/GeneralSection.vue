<script setup lang="ts">
import { computed, ref } from "vue"

import OnboardingDialog from "@/features/onboarding/OnboardingDialog.vue"
import { usePreferences, useUpdatePreferences } from "@/features/preferences/api"
import VoiceSelect from "@/features/speech/VoiceSelect.vue"
import { speechSupported } from "@/features/speech/voices"
import { messageOf } from "@/shared/api/errors"
import { applyLanguage, LANGUAGES, languageName, t } from "@/shared/i18n"
import type { Language } from "@/shared/i18n"
import { AppButton, AppForm, AppSelect, AppSettingRow, useToast } from "@/shared/ui"
import { THEME_CHOICES, useThemeStore } from "@/stores/theme"
import type { ThemeMode } from "@/stores/theme"

// What this account chose for itself, and what this browser holds for it.
// The theme lives here, next to the account, rather than in the header. Kept
// in this browser rather than on the server (D6).
// The voice reading aloud lives here for the same reason: voices are this
// browser's own. Nowhere to choose it where there is nothing to synthesise.
// The language is the account's, so it follows the person to any browser (D224).
const toast = useToast()
const theme = useThemeStore()
const speechOk = speechSupported()
const preferences = usePreferences()
const save = useUpdatePreferences()

// The welcome tour, on demand: finished or skipped long ago, it opens here
// again from its first clip rather than from the theme choice above.
const tourOpen = ref(false)

// A select holds no null, so the browser's language travels as a word of its
// own between here and the request.
const BROWSER = "browser"

const languageChoices = computed(() => [
  { value: BROWSER, label: t("language.browser"), description: t("language.browser_hint") },
  ...LANGUAGES.map((language) => ({ value: language, label: languageName(language) })),
])

const chosenLanguage = computed(() => {
  const data = preferences.data.value
  return data === undefined ? undefined : (data.language ?? BROWSER)
})

async function chooseLanguage(value: unknown) {
  if (value === chosenLanguage.value) return
  const language = value === BROWSER ? null : (value as Language)
  try {
    await save.mutateAsync({ language })
    // Before the toast, so it is already said in the language just chosen.
    await applyLanguage(language)
    toast.success(t("preferences.saved"))
  } catch (cause) {
    toast.error(messageOf(cause, t("preferences.not_saved")))
  }
}
</script>

<template>
  <div class="preferences-section">
    <AppSettingRow
      :title="t('language.label')"
      :summary="t('preferences.language_summary')"
    >
      <AppForm>
        <AppSelect
          :model-value="chosenLanguage"
          :options="languageChoices"
          :loading="save.isPending.value"
          :aria-label="t('language.label')"
          data-testid="preference-language"
          @update:model-value="chooseLanguage"
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
