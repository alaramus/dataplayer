<script setup lang="ts">
import { watch } from "vue"

import type { PreferencesPublic } from "@/client"
import { usePreferences, useUpdatePreferences } from "@/features/preferences/api"
import { messageOf } from "@/shared/api/errors"
import { applyLanguage, t } from "@/shared/i18n"
import { useToast } from "@/shared/ui"
import { useThemeStore } from "@/stores/theme"
import type { ThemeMode, ThemeName } from "@/stores/theme"

/**
 * Puts the account's language and theme on the interface (D224): once they
 * are known after sign-in, and whenever they change — here, or in another tab
 * through the query. Draws nothing; a component so App mounts it only while
 * signed in.
 *
 * The theme is chosen on the store, by Preferences, the welcome and the
 * toggle alike, and saved from here; the browser keeps the last account's
 * choice so the sign-in page and the first frame are not another's.
 */
type StoredTheme = NonNullable<PreferencesPublic["theme"]>
// The store's themes are the server's: one added on either side alone fails here.
const SAME: [ThemeName] extends [StoredTheme] ? ([StoredTheme] extends [ThemeName] ? true : never) : never = true
void SAME

const preferences = usePreferences()
const save = useUpdatePreferences()
const theme = useThemeStore()
const toast = useToast()

watch(
  () => preferences.data.value?.language,
  (language) => {
    if (language !== undefined) void applyLanguage(language)
  },
  { immediate: true }
)

function storedMode(): ThemeMode | undefined {
  const data = preferences.data.value
  return data === undefined ? undefined : (data.theme ?? "system")
}

// The account's choice arriving, after sign-in or from another tab.
watch(
  () => preferences.data.value?.theme,
  () => {
    const stored = storedMode()
    if (stored !== undefined && stored !== theme.mode) theme.set(stored)
  },
  { immediate: true }
)

// A choice made here, kept on the account. Nothing is saved before the
// account has been read: what the browser held is the last account's.
watch(
  () => theme.mode,
  async (mode) => {
    const stored = storedMode()
    if (stored === undefined || stored === mode) return
    try {
      await save.mutateAsync({ theme: mode === "system" ? null : mode })
    } catch (cause) {
      toast.error(messageOf(cause, t("preferences.not_saved")))
    }
  }
)
</script>

<template>
  <span hidden />
</template>
