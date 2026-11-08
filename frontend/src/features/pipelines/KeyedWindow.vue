<script setup lang="ts">
import { computed, ref } from "vue"

import type { FetchColumn, KeyedChoice, PasteColumn } from "@/client"
import { t } from "@/shared/i18n"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppForm,
  AppInput,
  AppNumberInput,
  AppPairs,
  AppPairsRow,
  AppSelect,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { defaultKey, defaultValues, fieldName, holdsHash, keyedProblem } from "./keyed"

/**
 * What a link keeping the latest per key writes (D314): the column naming
 * each key, what goes before it, what the key holds and how long it lives.
 * Kept on the link; nothing runs from here.
 */
const props = defineProps<{
  sourceColumns: readonly FetchColumn[]
  /** The place's own prefix, which the field starts as. */
  suggestedPrefix: string
  kept: { byKey: KeyedChoice | null; columns: readonly PasteColumn[] | null }
}>()

const emit = defineEmits<{
  close: []
  keep: [pick: { by_key: KeyedChoice; columns: PasteColumn[] }]
}>()

const keyColumn = ref<string | null>(props.kept.byKey?.key_column ?? defaultKey(props.sourceColumns))
const prefix = ref(props.kept.byKey?.prefix ?? props.suggestedPrefix)
const ttl = ref<number | null>(props.kept.byKey?.ttl_seconds ?? null)
// Every column, ticked or not, with the name it is written under.
const values = ref(
  (() => {
    const chosen = props.kept.columns?.length ? [...props.kept.columns] : defaultValues(props.sourceColumns, keyColumn.value)
    return props.sourceColumns.map((column) => {
      const found = chosen.find((one) => one.source === column.name)
      return { source: column.name, target: found?.target ?? fieldName(column.name), on: found !== undefined }
    })
  })()
)

const picked = computed(() =>
  values.value.filter((one) => one.on).map((one) => ({ source: one.source, target: one.target.trim() }))
)
const pick = computed(() => ({
  byKey: { key_column: keyColumn.value ?? "", prefix: prefix.value, ttl_seconds: ttl.value },
  columns: picked.value,
}))
const problem = computed(() => keyedProblem(pick.value))
const keyOptions = computed(() => props.sourceColumns.map((column) => ({ label: column.name, value: column.name })))
const shape = computed(() =>
  holdsHash(picked.value) ? t("pipelines.keyed.as_hash", { n: picked.value.length }) : t("pipelines.keyed.as_string")
)

function keep() {
  if (problem.value !== null) return
  emit("keep", { by_key: pick.value.byKey, columns: pick.value.columns })
}
</script>

<template>
  <WindowDialog
    :model-value="true"
    :title="t('pipelines.keyed.title')"
    :subtitle="t('pipelines.keyed.subtitle')"
    size="wide-form"
    sizing="stable"
    data-testid="keyed-window"
    @update:model-value="emit('close')"
  >
    <AppForm layout="section">
      <AppSelect
        :model-value="keyColumn"
        :options="keyOptions"
        :label="t('pipelines.keyed.key_column')"
        data-testid="keyed-key-column"
        @update:model-value="keyColumn = String($event)"
      />
      <AppInput
        v-model="prefix"
        :label="t('pipelines.keyed.prefix')"
        :hint="t('pipelines.keyed.prefix_hint', { example: `${prefix}${'BTC'}` })"
        autocomplete="off"
        data-testid="keyed-prefix"
      />
      <AppPairs>
        <template #aside>
          <span data-testid="keyed-shape">{{ shape }}</span>
        </template>
        <AppPairsRow
          v-for="value in values"
          :key="value.source"
          :idle="!value.on"
          :data-testid="`keyed-value-${value.source}`"
        >
          <template #from>
            <AppCheckbox
              v-model="value.on"
              :label="value.source"
              dense
            />
          </template>
          <template #to>
            <AppInput
              v-model="value.target"
              :aria-label="t('pipelines.keyed.field_aria', { column: value.source })"
              :disable="!value.on || picked.length < 2"
              compact
              autocomplete="off"
            />
          </template>
        </AppPairsRow>
      </AppPairs>
      <AppNumberInput
        :model-value="ttl"
        :label="t('pipelines.keyed.ttl')"
        :hint="t('pipelines.keyed.ttl_hint')"
        data-testid="keyed-ttl"
        @update:model-value="ttl = $event === null || $event <= 0 ? null : Math.round($event)"
      />
      <AppBanner
        v-if="problem"
        tone="warning"
        data-testid="keyed-problem"
      >
        {{ t(`pipelines.keyed.problem.${problem}`) }}
      </AppBanner>
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        @click="emit('close')"
      />
      <AppButton
        :label="t('pipelines.link_panel.keep')"
        :disable="problem !== null"
        data-testid="keyed-keep"
        @click="keep"
      />
    </template>
  </WindowDialog>
</template>
