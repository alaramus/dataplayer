<script setup lang="ts">
import AppIconButton from "./AppIconButton.vue"

withDefaults(
  defineProps<{
    tooltip?: string
    disable?: boolean
  }>(),
  { tooltip: "Copy", disable: false }
)
</script>

<template>
  <AppIconButton
    icon="content_copy"
    :tooltip="tooltip"
    :disable="disable"
  />
</template>
