<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ColumnTypeOption } from "@/client"
import { AppBanner, AppButton, AppSection, AppSelect } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  modelValue: boolean
  name: string
  /** What the column has now, spelled as the source spells it. */
  currentType: string
  types: ColumnTypeOption[]
  /** Rows holding a value the chosen type cannot read, as the source counted them. */
  blocked: { rows: number; exact: boolean } | null
  saving: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  save: [typeCode: string]
}>()

const typeCode = ref("")

watch(
  () => [props.modelValue, props.name] as const,
  ([open]) => {
    if (open) typeCode.value = props.types[0]?.code ?? ""
  },
  { immediate: true }
)

const blockedText = computed(() => {
  if (props.blocked === null) return ""
  const rows = props.blocked.exact
    ? `${props.blocked.rows} ${props.blocked.rows === 1 ? "row holds" : "rows hold"}`
    : `More than ${props.blocked.rows} rows hold`
  return `${rows} a value the chosen type cannot read. Correct or remove those values first.`
})
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="`Column type — ${name}`"
    data-testid="structure-type-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="structure-type-error"
      >
        {{ error }}
      </AppBanner>
      <!-- Nothing failed: the source read the values and reported what it
           found, so this is a warning rather than an error. -->
      <AppBanner
        v-if="blocked !== null"
        tone="warning"
        data-testid="structure-type-blocked"
      >
        {{ blockedText }}
      </AppBanner>
      <div>Now: <code>{{ currentType }}</code></div>
      <AppSelect
        :model-value="typeCode"
        :options="types.map((type) => ({ label: `${type.title} · ${type.sql}`, value: type.code }))"
        label="New type"
        :disable="saving"
        data-testid="structure-type-select"
        @update:model-value="typeCode = String($event)"
      />
      <!-- Said once, as a property of changing a type at all: which pairs lose
           what is PostgreSQL's rule, and restating it here would be a second
           implementation of it. -->
      <AppBanner tone="info">
        Every value is rewritten as the new type. A conversion can lose
        information — a number is rounded, a time of day is dropped.
      </AppBanner>
    </AppSection>
    <template #actions>
      <AppButton
        variant="secondary"
        label="Cancel"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        variant="danger"
        label="Change type"
        :disable="typeCode.length === 0"
        :loading="saving"
        data-testid="structure-type-save"
        @click="emit('save', typeCode)"
      />
    </template>
  </WindowDialog>
</template>
