<script setup lang="ts">
import { AppIconButton, appIcons, useToast } from "@/shared/ui"
import { copyText } from "@/shared/clipboard"
import { t } from "@/shared/i18n"

import ReadAloudButton from "@/features/speech/ReadAloudButton.vue"

/**
 * Copy and read aloud, under a message of either chat. The parent decides
 * when they show; they are the same two buttons wherever a message is. The
 * reader is the shared one, so a message and a document stop each other.
 */
const props = defineProps<{ text: string; role: "user" | "assistant" }>()

const toast = useToast()

async function copy() {
  const user = props.role === "user"
  try {
    await copyText(props.text)
    toast.success(user ? t("ai.message.message_copied") : t("ai.message.answer_copied"))
  } catch {
    toast.error(user ? t("ai.message.message_copy_failed") : t("ai.message.answer_copy_failed"))
  }
}
</script>

<template>
  <div class="ai-message-actions">
    <AppIconButton
      :icon="appIcons.copy"
      :tooltip="role === 'user' ? t('ai.message.copy_message') : t('ai.message.copy_answer')"
      data-testid="ai-message-copy"
      @click="copy"
    />
    <ReadAloudButton
      :text="text"
      strip-markdown
      :listen-label="role === 'user' ? t('ai.message.listen_message') : t('ai.message.listen_answer')"
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
