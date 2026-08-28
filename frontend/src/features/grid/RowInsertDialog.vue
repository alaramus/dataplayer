<script setup lang="ts">
import { computed, reactive, watch } from "vue"

import type { FetchColumn, InsertValue } from "@/client"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppInput,
  AppSection,
  AppSelect,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  modelValue: boolean
  columns: FetchColumn[]
  saving: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  save: [values: InsertValue[]]
}>()

const included = reactive<Record<string, boolean>>({})
const nulls = reactive<Record<string, boolean>>({})
const drafts = reactive<Record<string, string>>({})
const insertableColumns = computed(() =>
  props.columns.filter((column) => column.insertable === true)
)

watch(
  () => [props.modelValue, props.columns] as const,
  ([open]) => {
    if (!open) return
    for (const column of insertableColumns.value) {
      included[column.name] = column.insert_required === true
      nulls[column.name] = false
      drafts[column.name] = column.type.category === "boolean" ? "false" : ""
    }
  },
  { immediate: true }
)

function options(column: FetchColumn) {
  if (column.type.category === "boolean") {
    return [
      { label: "True", value: "true" },
      { label: "False", value: "false" },
    ]
  }
  return column.type.enum_values ?? []
}

function save() {
  emit(
    "save",
    insertableColumns.value.flatMap((column) =>
      included[column.name] === true
        ? [
            {
              column: column.name,
              value: nulls[column.name] === true ? null : (drafts[column.name] ?? ""),
            },
          ]
        : []
    )
  )
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    title="Insert row"
    subtitle="Omitted columns keep their source default"
    size="lg"
    data-testid="grid-row-insert"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="grid-insert-error"
      >
        {{ error }}
      </AppBanner>
      <div
        v-for="column in insertableColumns"
        :key="column.name"
        class="row-insert__field"
      >
        <AppCheckbox
          v-if="column.insert_required !== true"
          :model-value="included[column.name] === true"
          :label="`Supply ${column.name}`"
          :disable="saving"
          :data-testid="`grid-insert-include-${column.name}`"
          @update:model-value="included[column.name] = $event"
        />
        <div
          v-else
          class="row-insert__required"
        >
          Required
        </div>
        <div class="row-insert__value">
          <AppCheckbox
            v-if="column.nullable === true && included[column.name] === true"
            :model-value="nulls[column.name] === true"
            label="Set SQL NULL"
            :disable="saving"
            :data-testid="`grid-insert-null-${column.name}`"
            @update:model-value="nulls[column.name] = $event"
          />
          <AppSelect
            v-if="column.type.category === 'boolean' || column.type.category === 'enum'"
            :model-value="drafts[column.name]"
            :options="options(column)"
            :label="`${column.name} · ${column.type.sql}`"
            :disable="included[column.name] !== true || nulls[column.name] === true || saving"
            :data-testid="`grid-insert-value-${column.name}`"
            @update:model-value="drafts[column.name] = String($event)"
          />
          <AppInput
            v-else
            :model-value="drafts[column.name] ?? ''"
            :label="`${column.name} · ${column.type.sql}`"
            :disable="included[column.name] !== true || nulls[column.name] === true || saving"
            :data-testid="`grid-insert-value-${column.name}`"
            @update:model-value="drafts[column.name] = $event"
          />
        </div>
      </div>
      <div
        v-if="insertableColumns.length === 0"
        class="text-caption"
      >
        This row uses source defaults only.
      </div>
    </AppSection>
    <template #actions>
      <AppButton
        variant="secondary"
        label="Cancel"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        variant="primary"
        label="Insert"
        :loading="saving"
        data-testid="grid-insert-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.row-insert__field {
  display: grid;
  grid-template-columns: minmax(120px, 0.35fr) minmax(220px, 1fr);
  align-items: start;
  gap: 12px;
}

.row-insert__required {
  padding: 18px 10px;
  color: var(--dp-text-muted);
}

.row-insert__value {
  min-width: 0;
}
</style>
