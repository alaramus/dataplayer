<script setup lang="ts">
import { computed } from "vue"

import { buttonLayout, buttonLook } from "./tokens"
import type { ButtonLayout, ButtonVariant } from "./tokens"

const props = withDefaults(
  defineProps<{
    /** What the button means. The look follows from it. */
    variant?: ButtonVariant
    /** Toolbar commands stay on one line; navigation entries start at the left. */
    layout?: ButtonLayout
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
    layout: "default",
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
const contentLayout = computed(() => buttonLayout(props.layout))
</script>

<template>
  <!-- no-caps throughout: action labels arrive from the server already
       written as sentences, and shouting them back is worse than a default. -->
  <q-btn
    no-caps
    :align="contentLayout.align"
    :no-wrap="contentLayout.noWrap"
    :class="{ 'app-button--toolbar': layout === 'toolbar' }"
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

<style scoped>
.app-button--toolbar :deep(.q-btn__content) {
  gap: var(--dp-space-1);
}
</style>
