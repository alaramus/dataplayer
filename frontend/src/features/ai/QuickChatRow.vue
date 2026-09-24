<script setup lang="ts">
import type { QuickChatSummary } from "@/client"
import { AppButton, AppIconButton, appIcons } from "@/shared/ui"

defineProps<{ chat: QuickChatSummary }>()
const emit = defineEmits<{ select: []; delete: [] }>()
</script>

<template>
  <div class="quick-chat-row" :data-testid="`quick-chat-row-${chat.id}`">
    <AppButton
      class="quick-chat-row__title"
      variant="quiet"
      layout="navigation"
      :icon="appIcons.quickChat"
      :label="chat.title"
      :title="`Quick chat: ${chat.title}`"
      :data-testid="`quick-chat-history-${chat.id}`"
      @click="emit('select')"
    />
    <span class="quick-chat-row__actions">
      <AppIconButton
        :icon="appIcons.delete"
        tooltip="Delete quick chat"
        variant="danger-quiet"
        compact
        :data-testid="`quick-chat-delete-${chat.id}`"
        @click="emit('delete')"
      />
    </span>
  </div>
</template>

<style scoped>
.quick-chat-row { display: flex; align-items: center; border-radius: var(--dp-radius-control); }
.quick-chat-row > :first-child { flex: 1; min-width: 0; }
.quick-chat-row__title :deep(.q-btn__content) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.quick-chat-row__actions { display: none; flex: none; }
.quick-chat-row:hover .quick-chat-row__actions,
.quick-chat-row:has(:focus-visible) .quick-chat-row__actions { display: flex; }
</style>
