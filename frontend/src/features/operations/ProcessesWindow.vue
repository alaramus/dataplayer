<script setup lang="ts">
import { AppBadge, AppButton, AppEmptyState, AppProgress } from "@/shared/ui"
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
  refresh: []
  clear: []
}>()
</script>

<template>
  <div
    class="processes"
    data-testid="processes-window"
  >
    <div class="processes__toolbar">
      <span>Completed changes are kept when work stops.</span>
      <AppButton
        variant="quiet"
        size="sm"
        label="Clear finished"
        @click="$emit('clear')"
      />
      <AppButton
        variant="quiet"
        size="sm"
        label="Refresh"
        :loading="loading"
        @click="$emit('refresh')"
      />
    </div>
    <p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
    <AppEmptyState
      v-if="rows.length === 0 && !error"
      :text="loading ? 'Loading processes' : 'No processes'"
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
          :label="stopping.has(row.id) ? 'Stopping' : row.status"
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
          icon="pause"
          label="Pause after current"
          @click="$emit('pause', row)"
        />
        <AppButton
          v-if="row.canResume"
          variant="quiet"
          size="sm"
          icon="play_arrow"
          label="Resume"
          @click="$emit('resume', row)"
        />
        <AppButton
          v-if="row.canStop"
          variant="danger-quiet"
          size="sm"
          icon="stop"
          :label="row.source === 'server' ? 'Cancel job' : row.paused ? 'Stop queue' : 'Stop after current'"
          :loading="stopping.has(row.id)"
          @click="$emit('stop', row)"
        />
      </div>
    </article>
    <AppButton
      v-if="more"
      variant="quiet"
      label="Load more"
      :loading="loading"
      @click="$emit('more')"
    />
  </div>
</template>

<style scoped>
.processes { padding: var(--dp-space-3); overflow: auto; }
.processes__toolbar, .processes__heading, .processes__meta, .processes__controls {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}
.processes__toolbar, .processes__controls { flex-wrap: wrap; }
.processes__toolbar > span, .processes__controls > span { flex: 1; min-width: 180px; }
.processes__row { padding: var(--dp-space-3) 0; border-top: 1px solid var(--dp-border); }
.processes__heading { justify-content: space-between; }
.processes__heading strong { overflow-wrap: anywhere; }
.processes__detail { padding: var(--dp-space-2) 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.processes__meta { justify-content: space-between; margin-top: var(--dp-space-2); }
.processes__meta, .processes__controls > span, .processes__toolbar > span {
  font-size: 12px;
  color: var(--dp-text-muted);
}
</style>
