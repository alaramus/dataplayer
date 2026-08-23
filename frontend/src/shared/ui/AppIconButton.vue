<script setup lang="ts">
import { computed } from "vue"

import AppTooltip from "./AppTooltip.vue"
import { buttonLook } from "./tokens"
import type { ButtonVariant } from "./tokens"

const props = withDefaults(
  defineProps<{
    icon: string
    /** Required: an icon alone names nothing, to a reader or to a test. */
    tooltip: string
    variant?: Extract<ButtonVariant, "quiet" | "danger-quiet">
    disable?: boolean
    /** A round trip is under way: the icon gives way to a spinner. */
    loading?: boolean
  }>(),
  { variant: "quiet", disable: false, loading: false }
)

const look = computed(() => buttonLook(props.variant))
</script>

<template>
  <q-btn
    dense
    flat
    :color="look.color"
    :icon="icon"
    :disable="disable"
    :loading="loading"
  >
    <AppTooltip>{{ tooltip }}</AppTooltip>
  </q-btn>
</template>
