<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { AppButton, AppForm, AppRadioGroup } from "@/shared/ui"
import type { RadioOption } from "@/shared/ui"
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

const scopes = computed<RadioOption[]>(() => [
  {
    label: "Current page",
    value: "page",
    description: `${props.pageRange} · ${props.columnCount} visible columns`,
  },
  {
    label: "All matching rows",
    value: "all",
    description: props.allSupported
      ? `${props.filterCount === 0 ? "The whole relation" : `${props.filterCount} active filters`}` +
        " · streamed rather than held in memory"
      : props.allReason ?? "This source cannot export all matching rows",
    disable: !props.allSupported,
  },
])

function chooseScope(value: string) {
  if (value === "page" || value === "all") scope.value = value
}

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
    size="md"
    sizing="content"
    data-testid="grid-download-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppRadioGroup
        :model-value="scope"
        aria-label="Rows"
        :options="scopes"
        data-testid="download-scope"
        @update:model-value="chooseScope"
      />
    </AppForm>
    <template #actions>
      <AppButton
        label="Cancel"
        variant="quiet"
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
