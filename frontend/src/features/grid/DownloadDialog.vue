<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { t } from "@/shared/i18n"
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
  /**
   * What "all" is where it is not a relation streamed from its source: a
   * query result's rows were captured once and are written from memory.
   */
  allDescription?: string
  running: boolean
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  run: [scope: DownloadScope, destination: DownloadDestination]
}>()

const scope = ref<DownloadScope>("page")

const scopes = computed<RadioOption[]>(() => [
  {
    label: t("grid.download.page"),
    value: "page",
    description: t("grid.download.page_description", {
      range: props.pageRange,
      columns: t("grid.download.visible_columns", { n: props.columnCount }, props.columnCount),
    }),
  },
  {
    label: t("grid.download.all"),
    value: "all",
    description: !props.allSupported
      ? props.allReason ?? t("grid.download.all_unsupported")
      : props.allDescription ??
        t("grid.download.all_description", {
          what:
            props.filterCount === 0
              ? t("grid.download.whole_relation")
              : t("grid.download.active_filters", { n: props.filterCount }, props.filterCount),
        }),
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
    :title="t('grid.download.title')"
    :subtitle="t('grid.download.subtitle')"
    size="md"
    sizing="content"
    data-testid="grid-download-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppRadioGroup
        :model-value="scope"
        :aria-label="t('grid.download.rows')"
        :options="scopes"
        data-testid="download-scope"
        @update:model-value="chooseScope"
      />
    </AppForm>
    <template #actions>
      <AppButton
        :label="t('catalog.common.cancel')"
        variant="quiet"
        :disable="running"
        @click="emit('update:modelValue', false)"
      />
      <!-- Two buttons rather than one, because they are two different things
           to want: the file, or a copy of it among your own files. -->
      <AppButton
        :label="t('grid.download.save_to_files')"
        variant="secondary"
        :loading="running"
        data-testid="grid-download-keep"
        @click="emit('run', scope, 'files')"
      />
      <AppButton
        :label="t('grid.download.run')"
        :loading="running"
        data-testid="grid-download-run"
        @click="emit('run', scope, 'browser')"
      />
    </template>
  </WindowDialog>
</template>
