<script setup lang="ts">
import { computed, onBeforeUnmount } from "vue"

import { AppIconButton, appIcons } from "@/shared/ui"

import { useReadAloud } from "./readAloud"
import { speechSupported } from "./voices"

/**
 * One listen button for every text a person reads: a chat message, a
 * Markdown document, a file. The voice is the browser's one, chosen once in
 * the voice store, so a choice in one place is the choice everywhere.
 */
withDefaults(
  defineProps<{
    text: string
    /** Markdown loses its marks before it is spoken; plain sources do not. */
    stripMarkdown?: boolean
    listenLabel?: string
    testid?: string
  }>(),
  { stripMarkdown: false, listenLabel: "Listen", testid: "read-aloud" }
)

const voice = useReadAloud()
const supported = speechSupported()
/** This button, as the reader: its text may change while it is read. */
const reader = Symbol("read-aloud")
const speaking = computed(() => voice.speaking.value === reader)

// Text that goes away stops being read.
onBeforeUnmount(() => {
  if (speaking.value) voice.stop()
})
</script>

<template>
  <AppIconButton
    v-if="supported"
    :live="speaking"
    :icon="speaking ? appIcons.stopCircle : appIcons.volumeUp"
    :tooltip="speaking ? 'Stop reading aloud' : listenLabel"
    :data-testid="testid"
    @click="voice.listen(reader, text, { stripMarkdown })"
  />
</template>

