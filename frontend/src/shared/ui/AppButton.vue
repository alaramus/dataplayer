<script setup lang="ts">
import { computed, useAttrs, useSlots } from "vue"

import { buttonLayout, buttonLook } from "./tokens"
import type { ButtonLayout, ButtonVariant } from "./tokens"

const props = withDefaults(
  defineProps<{
    /** What the button means. The look follows from it. */
    variant?: ButtonVariant
    /**
     * Toolbar commands stay on one line; navigation entries start at the left
     * and keep to one line too, a long name ending in an ellipsis.
     */
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

const attrs = useAttrs()
const slots = useSlots()
/**
 * A navigation entry cut short by its ellipsis says the whole name on hover,
 * and only then: a title on every entry repeats what is already on screen.
 * Left alone where the caller gave a title or a tooltip of its own.
 */
function nameIfCut(event: PointerEvent) {
  if (props.layout !== "navigation" || !shownLabel.value || attrs.title !== undefined || slots.default) return
  const button = event.currentTarget
  if (!(button instanceof HTMLElement)) return
  const label = button.querySelector(".q-btn__content > .block")
  if (label instanceof HTMLElement && label.scrollWidth > label.clientWidth) button.title = shownLabel.value
  else button.removeAttribute("title")
}
</script>

<template>
  <!-- no-caps throughout: action labels arrive from the server already
       written as sentences, and shouting them back is worse than a default. -->
  <q-btn
    class="app-button"
    no-caps
    :aria-label="spokenLabel"
    :align="contentLayout.align"
    :no-wrap="contentLayout.noWrap"
    :class="{
      'app-button--toolbar': layout === 'toolbar',
      'app-button--navigation': layout === 'navigation',
      'app-button--inline': layout === 'inline',
    }"
    :color="look.color"
    :text-color="look.textColor"
    :unelevated="look.unelevated"
    :flat="look.flat"
    :dense="size === 'sm'"
    :label="shownLabel"
    :icon="icon"
    :icon-right="iconRight"
    :loading="loading"
    :disable="disable"
    :type="type"
    @pointerenter="nameIfCut"
  >
    <slot />
  </q-btn>
</template>

<style scoped>
.app-button--toolbar :deep(.q-btn__content) {
  gap: var(--dp-space-1);
}
/* A value that is also its editor: the cell's weight, and its text in line
   with the text of the cells that are not buttons (D186). As a 500-weight
   button "character varying(255)" outweighed the column name beside it. */
.app-button--inline {
  min-height: var(--dp-row-height-dense);
  padding-block: 0;
  padding-inline: var(--dp-space-1);
  margin-inline: calc(-1 * var(--dp-space-1));
  font-weight: 400;
}
/* A long name wrapped under its own icon and doubled the entry's height; a
   list reads down one line per entry.
   Trap: QBtn holds the label in a `.block` of its own (display: block
   !important), and an ellipsis on the content never reaches it — the name is
   cut through a letter instead. So the label carries the ellipsis. */
/* An entry of a list reads at the list's weight; the current one says so
   with the tab ground and 500 (D186), not every entry with a button's 500. */
.app-button--navigation {
  max-width: 100%;
  font-weight: 400;
}
.app-button--navigation :deep(.q-btn__content) {
  min-width: 0;
}
.app-button--navigation :deep(.q-btn__content > .block) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
