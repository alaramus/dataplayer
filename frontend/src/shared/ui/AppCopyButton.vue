<script setup lang="ts">
import { computed } from "vue"

import { t } from "@/shared/i18n"

import AppIconButton from "./AppIconButton.vue"
import { appIcons } from "./icons"

const props = withDefaults(
  defineProps<{
    tooltip?: string
    disable?: boolean
  }>(),
  { tooltip: undefined, disable: false }
)

// A fallback rather than a default, so it is read in the current language.
const shownTooltip = computed(() => props.tooltip ?? t("kit.copy.tooltip"))
</script>

<template>
  <AppIconButton
    :icon="appIcons.copy"
    :tooltip="shownTooltip"
    :disable="disable"
  />
</template>
