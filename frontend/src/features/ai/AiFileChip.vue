<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { AppIconButton, AppTooltip } from "@/shared/ui"
import { t } from "@/shared/i18n"

import { shownSize } from "./attachments"
import type { AttachmentKind } from "./attachments"

/**
 * One file of a message: in the composer before it is sent, and in the
 * transcript after (D142). An image shows itself; text shows its name.
 * Pressing it opens the file in a tab of the browser.
 */
withDefaults(
  defineProps<{
    name: string
    size: number
    kind: AttachmentKind
    /** Where the image can be drawn from; none while it is being fetched. */
    thumbnail?: string | null
    /** Why the message cannot be sent with this file, when it cannot. */
    problem?: string
    removable?: boolean
  }>(),
  { thumbnail: null, problem: "", removable: false }
)
const emit = defineEmits<{ open: []; remove: [] }>()
</script>

<template>
  <span
    class="ai-file-chip"
    :class="{ 'ai-file-chip--problem': problem }"
    data-testid="ai-file-chip"
  >
    <button
      type="button"
      class="ai-file-chip__open"
      :aria-label="t('ai.file.open', { name })"
      @click="emit('open')"
    >
      <img
        v-if="kind === 'image' && thumbnail"
        :src="thumbnail"
        alt=""
        class="ai-file-chip__thumbnail"
      >
      <q-icon
        v-else
        :name="kind === 'image' ? 'image' : 'description'"
        size="var(--dp-icon-md)"
        class="ai-file-chip__icon"
      />
      <span class="ai-file-chip__text">
        <span class="ai-file-chip__name">{{ name }}</span>
        <span class="ai-file-chip__size">{{ problem || shownSize(size) }}</span>
      </span>
    </button>
    <AppTooltip v-if="problem">{{ problem }}</AppTooltip>
    <AppIconButton
      v-if="removable"
      :icon="appIcons.close"
      :tooltip="t('ai.common.remove', { name })"
      compact
      @click="emit('remove')"
    />
  </span>
</template>

<style scoped>
.ai-file-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--dp-space-1);
  max-width: 240px;
  padding: var(--dp-space-1);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
  background: var(--dp-surface);
}
.ai-file-chip--problem {
  border-color: var(--dp-tone-warning-text);
}
.ai-file-chip__open {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.ai-file-chip__thumbnail {
  flex: none;
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: var(--dp-radius-control);
}
.ai-file-chip__icon {
  flex: none;
  color: var(--dp-text-muted);
}
.ai-file-chip__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.ai-file-chip__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--dp-font-size-sm);
}
.ai-file-chip__size {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
}
.ai-file-chip--problem .ai-file-chip__size {
  color: var(--dp-tone-warning-text);
}
</style>
