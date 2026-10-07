<script setup lang="ts">
import { onBeforeUnmount } from "vue"

import { AppIconButton, appIcons } from "@/shared/ui"

import { useReadAloud } from "./readAloud"
import { speechSupported } from "./voices"

/**
 * One listen button for every text a person reads: a chat message, a
 * Markdown document, a file. The voice is the browser's one, chosen once in
 * the voice store, so a choice in one place is the choice everywhere.
 */
const props = withDefaults(
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

// Text that goes away stops being read.
onBeforeUnmount(() => {
  if (voice.speaking.value === props.text) voice.stop()
})
</script>

<template>
  <AppIconButton
    v-if="supported"
    :class="{ 'read-aloud--speaking': voice.speaking.value === text }"
    :icon="voice.speaking.value === text ? appIcons.stopCircle : appIcons.volumeUp"
    :tooltip="voice.speaking.value === text ? 'Stop reading aloud' : listenLabel"
    :data-testid="testid"
    @click="voice.listen(text, { stripMarkdown })"
  />
</template>

<style scoped>
/* A stop in progress reads in the danger colour at rest: it is a state, not
   a destructive command, so D186's quiet-until-hover does not apply. The
   class stands on the button itself, which is the kit button's root. */
.read-aloud--speaking {
  color: var(--dp-action-danger);
}
</style>
