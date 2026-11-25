<script setup lang="ts">
import { watch } from "vue"

import { t } from "@/shared/i18n"
import { AppIconButton, appIcons, useToast } from "@/shared/ui"

import type { Dictation } from "./dictation"

/**
 * One microphone for every text a person speaks instead of typing: a message,
 * a file, a letter, a query, a document (D138).
 *
 * The recogniser is the caller's — only the text it writes into knows where
 * the words go — so this is the button over it, and the one place a failure is
 * said aloud, in the same words wherever the microphone stands.
 */
const props = withDefaults(
  defineProps<{
    dictation: Dictation
    /** What it dictates into, where that is not already obvious in the panel. */
    label?: string
    /** Something else is under way in this panel: sending, running, opening. */
    disable?: boolean
    testid?: string
  }>(),
  { label: "", disable: false, testid: "dictate" }
)

const emit = defineEmits<{
  /** Said before it listens: the words of this session begin here. */
  start: []
}>()

const toast = useToast()

// The browser's word is the composable's, the sentence is this button's. The
// reason is cleared so the same failure is said once.
watch(
  () => props.dictation.failure.value,
  (reason) => {
    if (reason === "") return
    toast.error(reason === "not-allowed" ? t("dictation.mic_refused") : t("dictation.stopped"))
    props.dictation.dismissFailure()
  }
)

function press() {
  if (!props.dictation.supported || props.disable) return
  if (!props.dictation.listening.value) emit("start")
  props.dictation.toggle()
}
</script>

<template>
  <AppIconButton
    :live="dictation.listening.value"
    :icon="dictation.listening.value ? appIcons.mic : appIcons.micNone"
    :tooltip="
      !dictation.supported
        ? t('dictation.cannot_listen')
        : dictation.listening.value
          ? t('dictation.stop')
          : label || t('dictation.dictate')
    "
    :disable="!dictation.supported || disable"
    :data-testid="testid"
    @click="press"
  />
</template>
