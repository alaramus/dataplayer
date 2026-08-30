<script setup lang="ts">
defineProps<{
  modelValue: File | null
  label?: string
}>()

const emit = defineEmits<{ "update:modelValue": [value: File | null] }>()
</script>

<template>
  <q-file
    :model-value="modelValue"
    :label="label"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template
      v-if="$slots.after"
      #after
    >
      <slot name="after" />
    </template>
  </q-file>
</template>
