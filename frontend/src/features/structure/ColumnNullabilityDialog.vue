<script setup lang="ts">
import { computed } from "vue"

import { AppBanner, AppButton, AppSection } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  modelValue: boolean
  name: string
  /** What the column says now; the one change on offer is the other one. */
  nullable: boolean
  /** Rows standing in the way of requiring a value, as the source counted them. */
  blocked: { rows: number; exact: boolean } | null
  saving: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  save: [nullable: boolean]
}>()

const state = computed(() =>
  props.nullable
    ? `${props.name} accepts rows with no value.`
    : `${props.name} requires a value in every row.`
)
const action = computed(() => (props.nullable ? "Require a value" : "Allow no value"))
const blockedText = computed(() => {
  if (props.blocked === null) return ""
  const rows = props.blocked.exact
    ? `${props.blocked.rows} ${props.blocked.rows === 1 ? "row has" : "rows have"}`
    : `More than ${props.blocked.rows} rows have`
  return `${rows} no value in ${props.name}. Give them one, or delete them, before requiring a value.`
})
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    title="Empty values"
    :subtitle="name"
    data-testid="structure-nullability-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="structure-nullability-error"
      >
        {{ error }}
      </AppBanner>
      <!-- Nothing failed: the source read the rows and reported what it found,
           so this is a warning rather than an error. -->
      <AppBanner
        v-if="blocked !== null"
        tone="warning"
        data-testid="structure-nullability-blocked"
      >
        {{ blockedText }}
      </AppBanner>
      <div>{{ state }}</div>
    </AppSection>
    <template #actions>
      <AppButton
        variant="secondary"
        label="Cancel"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="action"
        :loading="saving"
        data-testid="structure-nullability-save"
        @click="emit('save', !nullable)"
      />
    </template>
  </WindowDialog>
</template>
