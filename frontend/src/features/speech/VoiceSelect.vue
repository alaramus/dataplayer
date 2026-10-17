<script setup lang="ts">
import { computed } from "vue"

import { t } from "@/shared/i18n"
import { AppSelect } from "@/shared/ui"
import { useVoiceStore } from "@/stores/voice"

import { useVoices, voiceLabel } from "./voices"

/**
 * The voice reading aloud, wherever it is chosen.
 *
 * One control in Preferences and one in AI settings, both on the same store:
 * a choice in one place is the choice everywhere, in this browser. The list
 * itself is the browser's, arriving after the page, so the control only names
 * what is there. Without a label it is named by the caller's `aria-label`,
 * the way a toolbar field is.
 */
defineProps<{
  label?: string
}>()

const voice = useVoiceStore()
const { voices } = useVoices()
const options = computed(() => [
  { label: t("onboarding.speech.browser_default"), value: "" },
  ...voices.value.map((one) => ({ label: voiceLabel(one), value: one.voiceURI })),
])
</script>

<template>
  <AppSelect
    :model-value="voice.voice"
    :options="options"
    :label="label"
    @update:model-value="voice.setVoice($event as string)"
  />
</template>
