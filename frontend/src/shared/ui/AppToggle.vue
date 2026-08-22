<script setup lang="ts">
defineProps<{
  modelValue: boolean
  label?: string
}>()

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()
</script>

<template>
  <q-toggle
    :model-value="modelValue"
    :label="label"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
