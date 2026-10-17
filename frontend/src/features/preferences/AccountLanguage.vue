<script setup lang="ts">
import { watch } from "vue"

import { usePreferences } from "@/features/preferences/api"
import { applyLanguage } from "@/shared/i18n"

/**
 * Puts the account's language on the interface (D224): once it is known after
 * sign-in, and whenever it changes — here, or in another tab through the
 * query. Draws nothing; a component so App mounts it only while signed in.
 */
const preferences = usePreferences()

watch(
  () => preferences.data.value?.language,
  (language) => {
    if (language !== undefined) void applyLanguage(language)
  },
  { immediate: true }
)
</script>

<template>
  <span hidden />
</template>
