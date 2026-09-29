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
  <!-- Dense (D187): the full toggle keeps 12px of hit area to the left of its
       track and stands 40px tall, so its track began a finger's width right
       of every label and field it sat under, in a row taller than a control. -->
  <q-toggle
    v-bind="toggleLook()"
    dense
    :model-value="modelValue"
    :label="label"
    :disable="disable"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
