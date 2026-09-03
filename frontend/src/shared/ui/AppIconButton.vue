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
    /**
     * A button inside a cell rather than in a toolbar.
     *
     * A row of a grid is 72 pixels wide where its controls live, and three
     * ordinary buttons are wider than that — which is how the buttons of an
     * inserted row came to be drawn over the column beside it.
     */
    compact?: boolean
  }>(),
  { variant: "quiet", disable: false, loading: false, compact: false }
)

const look = computed(() => buttonLook(props.variant))
</script>

<template>
  <q-btn
    dense
    flat
    :size="compact ? 'xs' : undefined"
    :color="look.color"
    :icon="icon"
    :disable="disable"
    :loading="loading"
  >
    <AppTooltip>{{ tooltip }}</AppTooltip>
  </q-btn>
</template>
