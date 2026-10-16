<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { AppBadge, AppButton, AppEmptyState, AppProgress } from "@/shared/ui"
import { t } from "@/shared/i18n"
import type { ProcessRow } from "./presentation"

defineProps<{
  rows: ProcessRow[]
  error: string
  loading: boolean
  more: boolean
  stopping: ReadonlySet<string>
}>()
defineEmits<{
  pause: [row: ProcessRow]
  resume: [row: ProcessRow]
  stop: [row: ProcessRow]
  more: []
}>()
</script>

<template>
  <div
    class="processes"
    data-testid="processes"
  >
    <p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
    <AppEmptyState
      v-if="rows.length === 0 && !error"
      :text="loading ? t('activity.processes.loading') : t('activity.processes.nothing_running')"
    />
    <article
      v-for="row in rows"
      :key="`${row.source}:${row.id}`"
      class="processes__row"
      :data-testid="`process-${row.id}`"
    >
      <div class="processes__heading">
        <strong>{{ row.label }}</strong>
        <AppBadge
          :tone="row.tone"
          :label="stopping.has(row.id) ? t('activity.processes.stopping') : row.status"
        />
      </div>
      <div class="processes__detail">
        {{ row.detail }}
      </div>
      <AppProgress
        v-if="row.active"
        :label="row.label"
        :value="row.progress"
        :paused="row.paused"
      />
      <div class="processes__meta">
        <span>{{ row.measurement }}</span>
        <time :datetime="new Date(row.createdAt).toISOString()">{{ new Date(row.createdAt).toLocaleTimeString() }}</time>
      </div>
      <div
        v-if="row.active"
        class="processes__controls"
      >
        <span>{{ row.controlsHint }}</span>
        <AppButton
          v-if="row.canPause"
          variant="quiet"
          size="sm"
          :icon="appIcons.pause"
          :label="t('activity.processes.pause')"
          @click="$emit('pause', row)"
        />
        <AppButton
          v-if="row.canResume"
          variant="quiet"
          size="sm"
          :icon="appIcons.playArrow"
          :label="t('activity.processes.resume')"
          @click="$emit('resume', row)"
        />
        <AppButton
          v-if="row.canStop"
          variant="danger-quiet"
          size="sm"
          :icon="appIcons.stop"
          :label="row.source === 'server'
            ? t('activity.processes.cancel_job')
            : row.paused ? t('activity.processes.stop_queue') : t('activity.processes.stop_after')"
          :loading="stopping.has(row.id)"
          @click="$emit('stop', row)"
        />
      </div>
    </article>
    <AppButton
      v-if="more && rows.length > 0"
      variant="quiet"
      size="sm"
      :label="t('activity.processes.load_more')"
      :loading="loading"
      @click="$emit('more')"
    />
  </div>
</template>

<style scoped>
.processes__heading, .processes__meta, .processes__controls {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}
.processes__controls { flex-wrap: wrap; }
.processes__controls > span { flex: 1; min-width: 140px; }
.processes__row { padding: var(--dp-space-2) 0; border-top: 1px solid var(--dp-border-faint); }
.processes__row:first-of-type { border-top: none; }
.processes__heading { justify-content: space-between; }
.processes__heading strong { overflow-wrap: anywhere; }
.processes__detail { padding: var(--dp-space-1) 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.processes__meta { justify-content: space-between; margin-top: var(--dp-space-1); }
.processes__meta, .processes__controls > span {
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
}
</style>
