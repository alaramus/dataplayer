<script setup lang="ts">
import { computed } from "vue"

import { AppBanner, AppButton, AppForm } from "@/shared/ui"
import { t } from "@/shared/i18n"
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
    ? t("structure.nullability_dialog.accepts", { name: props.name })
    : t("structure.nullability_dialog.requires", { name: props.name })
)
const action = computed(() => (
  props.nullable
    ? t("structure.nullability_dialog.require")
    : t("structure.nullability_dialog.allow")
))
const blockedText = computed(() => {
  if (props.blocked === null) return ""
  const n = props.blocked.rows
  return t(
    props.blocked.exact
      ? "structure.nullability_dialog.blocked"
      : "structure.nullability_dialog.blocked_more",
    { n, name: props.name },
    n
  )
})
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    sizing="stable"
    size="compact-form"
    :title="t('structure.nullability_dialog.title', { name })"
    data-testid="structure-nullability-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
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
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
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
