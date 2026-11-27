<script setup lang="ts">
import { computed } from "vue"

import { formatDuration, formatSize } from "@/features/catalog/nodes"
import { copyText } from "@/shared/clipboard"
import { t } from "@/shared/i18n"
import { formatDateTime, formatNumber } from "@/shared/i18n/format"
import { AppCopyButton, AppStateTag, useToast } from "@/shared/ui"

import { momentAgo } from "./view"
import type { ViewValue } from "./view"

/**
 * One value of a document's view, drawn by its kind and nothing else (D420).
 * A link is handed up rather than followed here: what opens a node is the
 * panel's, which knows the connection.
 */
const props = defineProps<{ value: ViewValue }>()
const emit = defineEmits<{ open: [nodeId: string, label: string] }>()

const toast = useToast()

const number = computed(() => {
  const value = props.value
  if (value.kind !== "number") return ""
  return value.unit ? `${formatNumber(value.value)} ${value.unit}` : formatNumber(value.value)
})

async function copy(text: string) {
  try {
    await copyText(text, { from: "view" })
    toast.success(t("content.view.copied"))
  } catch {
    toast.error(t("content.view.copy_failed"))
  }
}
</script>

<template>
  <span
    class="view-value"
    :data-kind="value.kind ?? 'empty'"
  >
    <template v-if="value.kind === 'text'">
      <span class="view-value__text">{{ value.text }}</span>
      <span
        v-if="value.truncated"
        class="dp-meta"
      >{{ t("content.view.truncated") }}</span>
    </template>
    <template v-else-if="value.kind === 'code'">
      <code class="view-value__code">{{ value.text }}</code>
      <span
        v-if="value.truncated"
        class="dp-meta"
      >{{ t("content.view.truncated") }}</span>
      <AppCopyButton
        class="view-value__copy"
        compact
        @click="copy(value.text)"
      />
    </template>
    <template v-else-if="value.kind === 'number'">{{ number }}</template>
    <template v-else-if="value.kind === 'bytes'">{{ formatSize(value.value) }}</template>
    <template v-else-if="value.kind === 'duration'">{{ formatDuration(value.seconds) }}</template>
    <template v-else-if="value.kind === 'moment'">
      <time :datetime="value.value">{{ formatDateTime(value.value) }}</time>
      <span class="dp-meta">{{ momentAgo(value.value) }}</span>
    </template>
    <template v-else-if="value.kind === 'boolean'">
      {{ value.value ? t("content.view.yes") : t("content.view.no") }}
    </template>
    <AppStateTag
      v-else-if="value.kind === 'state'"
      :label="value.word"
      :tone="value.tone"
    />
    <span
      v-else-if="value.kind === 'list'"
      class="view-value__chips"
    >
      <span
        v-for="(item, index) in value.items"
        :key="index"
        class="view-value__chip"
      >{{ item }}</span>
      <span
        v-if="(value.omitted ?? 0) > 0"
        class="dp-meta"
      >{{ t("content.view.omitted", { n: value.omitted ?? 0 }) }}</span>
      <span
        v-if="value.items.length === 0"
        class="view-value__empty"
      >—</span>
    </span>
    <a
      v-else-if="value.kind === 'link'"
      class="view-value__link"
      href="#"
      data-testid="view-link"
      @click.prevent="emit('open', value.node_id, value.text)"
    >{{ value.text }}</a>
    <span
      v-else
      class="view-value__empty"
      :aria-label="t('content.view.not_set')"
    >—</span>
  </span>
</template>

<style scoped>
.view-value {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--dp-space-1);
  min-width: 0;
}
.view-value__text {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
/* The copy button stays at the end of the line it copies, however long. */
.view-value[data-kind="code"] {
  flex-wrap: nowrap;
  align-items: flex-start;
}
.view-value__code {
  flex: 1 1 auto;
  min-width: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.view-value__chips {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--dp-space-1);
}
.view-value__chip {
  padding: 0 var(--dp-space-2);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-pill);
  font-size: var(--dp-font-size-sm);
}
.view-value__link {
  color: var(--dp-link);
  overflow-wrap: anywhere;
}
.view-value__empty {
  color: var(--dp-text-faint);
}
</style>
