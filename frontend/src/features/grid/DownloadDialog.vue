<script setup lang="ts">
import { ref, watch } from "vue"

import { AppButton, AppSection, AppTooltip } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import type { DownloadDestination, DownloadScope } from "./download"

const props = defineProps<{
  modelValue: boolean
  pageRange: string
  columnCount: number
  filterCount: number
  allSupported: boolean
  allReason?: string
  running: boolean
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  run: [scope: DownloadScope, destination: DownloadDestination]
}>()

const scope = ref<DownloadScope>("page")

watch(
  () => props.modelValue,
  (open) => {
    if (open) scope.value = "page"
  }
)
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    title="Download CSV"
    subtitle="The visible columns stay in their current order"
    size="sm"
    data-testid="grid-download-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <div class="download-scope">
        <AppButton
          label="Current page"
          :variant="scope === 'page' ? 'primary' : 'secondary'"
          data-testid="download-scope-page"
          @click="scope = 'page'"
        />
        <span>{{ pageRange }} · {{ columnCount }} visible columns</span>
      </div>
      <div class="download-scope">
        <span>
          <AppButton
            label="All matching rows"
            :variant="scope === 'all' ? 'primary' : 'secondary'"
            :disable="!allSupported"
            data-testid="download-scope-all"
            @click="scope = 'all'"
          />
          <AppTooltip v-if="!allSupported">
            {{ allReason ?? "This source cannot export all matching rows" }}
          </AppTooltip>
        </span>
        <span v-if="allSupported">
          {{ filterCount === 0 ? "The whole relation" : `${filterCount} active filters` }}
          · streamed rather than held in memory
        </span>
        <span v-else>{{ allReason ?? "This source cannot export all matching rows" }}</span>
      </div>
    </AppSection>
    <template #actions>
      <AppButton
        label="Cancel"
        variant="secondary"
        :disable="running"
        @click="emit('update:modelValue', false)"
      />
      <!-- Two buttons rather than one, because they are two different things
           to want: the file, or a copy of it among your own files. -->
      <AppButton
        label="Save to my files"
        variant="secondary"
        :loading="running"
        data-testid="grid-download-keep"
        @click="emit('run', scope, 'files')"
      />
      <AppButton
        label="Download"
        :loading="running"
        data-testid="grid-download-run"
        @click="emit('run', scope, 'browser')"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.download-scope {
  display: grid;
  grid-template-columns: 160px 1fr;
  align-items: center;
  gap: 12px;
  min-height: 52px;
  padding: 8px;
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
}
</style>
