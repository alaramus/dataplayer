<script setup lang="ts">
import { computed } from "vue"

import { buttonLook } from "./tokens"
import type { ButtonVariant } from "./tokens"

const props = withDefaults(
  defineProps<{
    /** What the button means. The look follows from it. */
    variant?: ButtonVariant
    label?: string
    icon?: string
    size?: "sm" | "md"
    loading?: boolean
    disable?: boolean
    type?: "button" | "submit"
  }>(),
  {
    variant: "primary",
    label: undefined,
    icon: undefined,
    size: "md",
    loading: false,
    disable: false,
    type: "button",
  }
)

const look = computed(() => buttonLook(props.variant))
</script>

<template>
  <!-- no-caps throughout: action labels arrive from the server already
       written as sentences, and shouting them back is worse than a default. -->
  <q-btn
    no-caps
    :color="look.color"
    :flat="look.flat"
    :dense="size === 'sm'"
    :label="label"
    :icon="icon"
    :loading="loading"
    :disable="disable"
    :type="type"
  >
    <slot />
  </q-btn>
</template>
