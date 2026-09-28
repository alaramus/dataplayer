<script setup lang="ts">
import { onBeforeUnmount } from "vue"

import { AppIconButton, appIcons, useToast } from "@/shared/ui"

import { useReadAloud } from "./readAloud"

/**
 * Copy and read aloud, under a message of either chat. The parent decides
 * when they show; they are the same two buttons wherever a message is.
 */
const props = defineProps<{ text: string; role: "user" | "assistant" }>()

const toast = useToast()
const voice = useReadAloud()

async function copy() {
  const what = props.role === "user" ? "Message" : "Answer"
  try {
    await navigator.clipboard.writeText(props.text)
    toast.success(`${what} copied`)
  } catch {
    toast.error(`The ${what.toLowerCase()} could not be copied`)
  }
}

// A message that goes away stops being read.
onBeforeUnmount(() => {
  if (voice.speaking.value === props.text) voice.stop()
})
</script>

<template>
  <div class="ai-message-actions">
    <AppIconButton
      :icon="appIcons.copy"
      :tooltip="role === 'user' ? 'Copy message' : 'Copy answer'"
      data-testid="ai-message-copy"
      @click="copy"
    />
    <AppIconButton
      :icon="voice.speaking.value === text ? appIcons.stopCircle : appIcons.volumeUp"
      :tooltip="voice.speaking.value === text
        ? 'Stop reading aloud'
        : role === 'user' ? 'Listen to message' : 'Listen to answer'"
      :active="voice.speaking.value === text"
      data-testid="ai-message-listen"
      @click="voice.listen(text)"
    />
  </div>
</template>

<style scoped>
.ai-message-actions {
  display: flex;
  gap: var(--dp-space-1);
}
</style>
