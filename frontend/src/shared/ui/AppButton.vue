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
    /**
     * Draw the icon alone, and let the label stay the button's name.
     *
     * A narrow rail is a reason to show less, not to be called nothing: four
     * commands dropped their label to fit one and were announced as unnamed
     * buttons, the tooltip beside them naming nothing to a screen reader
     * (U04).
     */
    iconOnly?: boolean
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
    iconOnly: false,
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
const shownLabel = computed(() => (props.iconOnly ? undefined : props.label))
/** Only where the label is not drawn: a visible one names the button already. */
const spokenLabel = computed(() => (props.iconOnly ? props.label : undefined))
</script>

<template>
  <!-- no-caps throughout: action labels arrive from the server already
       written as sentences, and shouting them back is worse than a default. -->
  <q-btn
    no-caps
    :aria-label="spokenLabel"
    :align="contentLayout.align"
    :no-wrap="contentLayout.noWrap"
    :class="{ 'app-button--toolbar': layout === 'toolbar' }"
    :color="look.color"
    :flat="look.flat"
    :dense="size === 'sm'"
    :label="shownLabel"
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
