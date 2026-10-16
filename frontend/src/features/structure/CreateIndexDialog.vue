<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { IndexMethodOption } from "@/client"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppForm,
  AppSelect,
} from "@/shared/ui"
import { t } from "@/shared/i18n"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  modelValue: boolean
  columns: string[]
  methods: IndexMethodOption[]
  /** Groups of rows that repeat under the chosen columns, as the source counted them. */
  blocked: { groups: number; exact: boolean } | null
  saving: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  save: [value: { columns: string[]; method: string; unique: boolean }]
}>()

const chosen = ref<string[]>([])
const method = ref("")
const unique = ref(false)

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    chosen.value = []
    method.value = props.methods[0]?.code ?? ""
    unique.value = false
  },
  { immediate: true }
)

const current = computed(() =>
  props.methods.find((option) => option.code === method.value)
)
// The two limits arrived with the method, so the screen states them rather
// than knowing a rule of its own about which method can do what.
const uniqueAllowed = computed(() => current.value?.unique_supported === true)
const tooManyColumns = computed(
  () => chosen.value.length > 1 && current.value?.multi_column_supported !== true
)

watch(uniqueAllowed, (allowed) => {
  if (!allowed) unique.value = false
})

const blockedText = computed(() => {
  if (props.blocked === null) return ""
  const n = props.blocked.groups
  return t(
    props.blocked.exact ? "structure.index_dialog.blocked" : "structure.index_dialog.blocked_more",
    { n },
    n
  )
})
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    sizing="stable"
    size="compact-form"
    :title="t('structure.index_dialog.title')"
    :subtitle="t('structure.index_dialog.subtitle')"
    data-testid="structure-index-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="structure-index-error"
      >
        {{ error }}
      </AppBanner>
      <!-- Nothing failed: the source counted the repeats and built nothing. -->
      <AppBanner
        v-if="blocked !== null"
        tone="warning"
        data-testid="structure-index-blocked"
      >
        {{ blockedText }}
      </AppBanner>
      <AppSelect
        :model-value="chosen"
        :options="columns"
        :label="t('structure.index_dialog.columns')"
        multiple
        :disable="saving"
        data-testid="structure-index-columns"
        @update:model-value="chosen = $event as string[]"
      />
      <AppSelect
        :model-value="method"
        :options="methods.map((option) => ({ label: option.title, value: option.code }))"
        :label="t('structure.index_dialog.method')"
        :error="tooManyColumns ? t('structure.index_dialog.one_column', { method: current?.title ?? '' }) : ''"
        :disable="saving"
        data-testid="structure-index-method"
        @update:model-value="method = String($event)"
      />
      <AppCheckbox
        :model-value="unique"
        :label="uniqueAllowed ? t('structure.index_dialog.unique') : t('structure.index_dialog.unique_refused', { method: current?.title ?? '' })"
        :disable="saving || !uniqueAllowed"
        data-testid="structure-index-unique"
        @update:model-value="unique = $event"
      />
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="t('structure.index_dialog.create')"
        :disable="chosen.length === 0 || method.length === 0 || tooManyColumns"
        :loading="saving"
        data-testid="structure-index-save"
        @click="emit('save', { columns: chosen, method, unique })"
      />
    </template>
  </WindowDialog>
</template>
