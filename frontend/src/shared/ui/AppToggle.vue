<script setup lang="ts">
import { toggleLook } from "./tokens"

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
    v-bind="toggleLook()"
    :model-value="modelValue"
    :label="label"
    :disable="disable"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
