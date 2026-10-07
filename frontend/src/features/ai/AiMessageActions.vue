<script setup lang="ts">
import { AppIconButton, appIcons, useToast } from "@/shared/ui"

import ReadAloudButton from "@/features/speech/ReadAloudButton.vue"

/**
 * Copy and read aloud, under a message of either chat. The parent decides
 * when they show; they are the same two buttons wherever a message is. The
 * reader is the shared one, so a message and a document stop each other.
 */
const props = defineProps<{ text: string; role: "user" | "assistant" }>()

const toast = useToast()

async function copy() {
  const what = props.role === "user" ? "Message" : "Answer"
  try {
    await navigator.clipboard.writeText(props.text)
    toast.success(`${what} copied`)
  } catch {
    toast.error(`The ${what.toLowerCase()} could not be copied`)
  }
}
</script>

<template>
  <div class="ai-message-actions">
    <AppIconButton
      :icon="appIcons.copy"
      :tooltip="role === 'user' ? 'Copy message' : 'Copy answer'"
      data-testid="ai-message-copy"
      @click="copy"
    />
    <ReadAloudButton
      :text="text"
      strip-markdown
      :listen-label="role === 'user' ? 'Listen to message' : 'Listen to answer'"
      testid="ai-message-listen"
    />
  </div>
</template>

<style scoped>
.ai-message-actions {
  display: flex;
  gap: var(--dp-space-1);
}
</style>
