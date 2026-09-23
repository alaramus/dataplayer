<script setup lang="ts">
import AppIconButton from "./AppIconButton.vue"
import { appIcons } from "./icons"

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
    :icon="appIcons.copy"
    :tooltip="tooltip"
    :disable="disable"
  />
</template>
