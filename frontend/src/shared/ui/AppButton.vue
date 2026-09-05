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
    /**
     * An icon after the label rather than before it.
     *
     * Which side is not decoration: an icon before the label belongs to the
     * action ("delete"), and one after it points where the action goes
     * ("next ›"). A button that walks forwards with its chevron on the left
     * reads as walking backwards.
     */
    iconRight?: string
    size?: "sm" | "md"
    loading?: boolean
    disable?: boolean
    type?: "button" | "submit"
  }>(),
  {
    variant: "primary",
    label: undefined,
    icon: undefined,
    iconRight: undefined,
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
    :icon-right="iconRight"
    :loading="loading"
    :disable="disable"
    :type="type"
  >
    <slot />
  </q-btn>
</template>
