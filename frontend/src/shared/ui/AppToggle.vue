<script setup lang="ts">
import { inject } from "vue"

import { formLayoutKey } from "./formLayout"
import { toggleLook } from "./tokens"

const formLayout = inject(formLayoutKey, false)

withDefaults(
  defineProps<{
    modelValue: boolean
    label?: string
    disable?: boolean
  }>(),
  { label: undefined, disable: false }
)

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()
</script>

<template>
  <q-toggle
    v-bind="toggleLook(formLayout)"
    :model-value="modelValue"
    :label="label"
    :disable="disable"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
