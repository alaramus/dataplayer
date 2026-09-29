<script setup lang="ts">
import { computed } from "vue"

import { messageOf } from "@/shared/api/errors"
import { useNow } from "@/shared/freshness/useNow"
import { AppBanner, AppEmptyState, AppSpinner, appIcons } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useHistory } from "./api"
import { historyLine } from "./history"

/**
 * A pipeline's runs and its schedule's skips and misses, newest first
 * (D180). A run pressed is shown on the canvas behind, and the window stays
 * open so another can be pressed after it.
 */
const props = defineProps<{
  pipelineId: string
  pipelineName: string
  /** The run the canvas shows now. */
  shownJobId: string | null
}>()

const emit = defineEmits<{
  show: [jobId: string]
  close: []
}>()

const history = useHistory(() => props.pipelineId)
const now = useNow()
const lines = computed(() => (history.data.value ?? []).map((row) => historyLine(row, now.value)))
</script>

<template>
  <WindowDialog
    :model-value="true"
    title="History"
    :subtitle="`What ${pipelineName} did, newest first`"
    size="medium-form"
    sizing="stable"
    data-testid="history-window"
    @update:model-value="emit('close')"
  >
    <div class="history-window">
      <AppSpinner v-if="history.isPending.value" />
      <AppBanner
        v-else-if="history.isError.value"
        tone="error"
      >
        {{ messageOf(history.error.value, "The history could not be read") }}
      </AppBanner>
      <AppEmptyState
        v-else-if="lines.length === 0"
        :icon="appIcons.history"
        text="Not run yet"
      />
      <template v-else>
        <template
          v-for="line in lines"
          :key="line.key"
        >
          <button
            v-if="line.jobId !== null"
            type="button"
            class="history-window__row history-window__row--run"
            :class="{ 'history-window__row--shown': line.jobId === shownJobId }"
            :aria-pressed="line.jobId === shownJobId"
            data-testid="history-run"
            @click="emit('show', line.jobId)"
          >
            <span
              class="history-window__said"
              :class="`history-window__said--${line.tone}`"
            ><q-icon
              v-if="line.tone === 'caution'"
              class="history-window__caution"
              :name="appIcons.warningAmber"
              size="var(--dp-icon-sm)"
            />{{ line.said }}</span>
            <span class="history-window__detail">{{ line.detail }}</span>
          </button>
          <div
            v-else
            class="history-window__row"
            data-testid="history-note"
          >
            <span
              class="history-window__said"
              :class="`history-window__said--${line.tone}`"
            ><q-icon
              v-if="line.tone === 'caution'"
              class="history-window__caution"
              :name="appIcons.warningAmber"
              size="var(--dp-icon-sm)"
            />{{ line.said }}</span>
            <span class="history-window__detail">{{ line.detail }}</span>
          </div>
        </template>
      </template>
    </div>
  </WindowDialog>
</template>

<style scoped>
.history-window {
  display: flex;
  flex-direction: column;
  padding: var(--dp-space-1);
}
.history-window__row {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: var(--dp-space-1) var(--dp-space-2);
  border: none;
  border-radius: var(--dp-radius-control);
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
}
.history-window__row--run {
  cursor: pointer;
}
.history-window__row--run:hover {
  background: var(--dp-hover);
}
/* The run shown on the canvas, drawn as a current tab is (D186). */
.history-window__row--shown,
.history-window__row--shown:hover {
  background: var(--dp-tab-current);
}
.history-window__said {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
/* A run that stopped short says so with its icon; the sentence stays the
   list's text, a whole line of amber being louder than what it reports. */
.history-window__caution {
  margin-inline-end: var(--dp-space-1);
  color: var(--dp-tone-warning-text);
}
.history-window__said--muted {
  color: var(--dp-text-muted);
}
.history-window__detail {
  overflow: hidden;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
