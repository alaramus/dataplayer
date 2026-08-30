<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { IndexMethodOption } from "@/client"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppSection,
  AppSelect,
} from "@/shared/ui"
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
  const groups = props.blocked.exact
    ? `${props.blocked.groups} ${props.blocked.groups === 1 ? "value" : "values"}`
    : `More than ${props.blocked.groups} values`
  return `${groups} already appear more than once, so this index cannot be unique.`
})
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    title="Add index"
    subtitle="The source names it and picks the methods"
    data-testid="structure-index-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
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
        label="Columns, in index order"
        multiple
        :disable="saving"
        data-testid="structure-index-columns"
        @update:model-value="chosen = $event as string[]"
      />
      <AppSelect
        :model-value="method"
        :options="methods.map((option) => ({ label: option.title, value: option.code }))"
        label="Method"
        :error="tooManyColumns ? `${current?.title} indexes one column only` : ''"
        :disable="saving"
        data-testid="structure-index-method"
        @update:model-value="method = String($event)"
      />
      <AppCheckbox
        :model-value="unique"
        :label="uniqueAllowed ? 'Unique' : `Unique — ${current?.title} cannot`"
        :disable="saving || !uniqueAllowed"
        data-testid="structure-index-unique"
        @update:model-value="unique = $event"
      />
    </AppSection>
    <template #actions>
      <AppButton
        variant="secondary"
        label="Cancel"
        :disable="saving"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        label="Create"
        :disable="chosen.length === 0 || method.length === 0 || tooManyColumns"
        :loading="saving"
        data-testid="structure-index-save"
        @click="emit('save', { columns: chosen, method, unique })"
      />
    </template>
  </WindowDialog>
</template>
