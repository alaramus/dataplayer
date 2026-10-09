<script setup lang="ts">
import { computed, useAttrs } from "vue"

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
    /** The command represents a configured or enabled state. */
    active?: boolean
    /**
     * Something the button started is running — dictation, reading aloud —
     * and pressing it stops that: red at rest, as a recording light is. A
     * state, not a destructive command, so D186's quiet-until-hover does not
     * apply.
     */
    live?: boolean
    /**
     * A button inside a cell rather than in a toolbar.
     *
     * A row of a grid is 72 pixels wide where its controls live, and three
     * ordinary buttons are wider than that — which is how the buttons of an
     * inserted row came to be drawn over the column beside it.
     */
    compact?: boolean
  }>(),
  { variant: "quiet", disable: false, loading: false, active: false, live: false, compact: false }
)

const look = computed(() => buttonLook(props.variant))
/**
 * A destructive command in a toolbar or a row is drawn like its neighbours and
 * turns red under the pointer or the keyboard (D186): red at rest on every row
 * of a list, it was the loudest thing on the screen. Its danger is said again
 * where it is confirmed.
 */
const quietColor = computed(() => (props.variant === "danger-quiet" ? undefined : look.value.color))

// The wrapper below would otherwise take data-testid and aria-label off the
// button they name.
defineOptions({ inheritAttrs: false })

const attrs = useAttrs()
/**
 * What the control is called: the caller's own name where it gave one, and the
 * tooltip otherwise. Read here as well as bound below, because the disabled
 * shape is named on its wrapper and a name that only reached the button would
 * be a name nothing announces.
 */
const spokenName = computed(() =>
  typeof attrs["aria-label"] === "string" ? attrs["aria-label"] : props.tooltip
)
</script>

<template>
  <!--
    Two shapes of the same button, because a disabled one takes no pointer
    events: a tooltip hung on it never opens, and the reason a command is off
    is exactly what a disabled button has to be able to say. So that one hangs
    off a wrapper instead — the answer the command bar already gives (D69),
    moved into the kit so no screen has to know about it.

    The wrapper is what a keyboard reaches, too. A disabled button is out of
    the tab order, which left the reason on hover and nowhere else; the wrapper
    takes the button's place in the order and its name — the label and the
    reason together — and the button inside it is hidden from a reader so the
    pair is announced once (U14).

    Only the disabled shape is wrapped. The wrapper is a box in the layout, and
    the enabled button is in a hundred places that were laid out around it.
  -->
  <span
    v-if="disable"
    class="app-icon-button"
    role="button"
    aria-disabled="true"
    tabindex="0"
    :aria-label="spokenName"
  >
    <q-btn
      aria-hidden="true"
      v-bind="$attrs"
      dense
      flat
      disable
      :class="{ 'app-icon-button__compact': compact, 'app-icon-button--danger': variant === 'danger-quiet', 'app-icon-button--live': live }"
      :color="live ? undefined : active ? 'positive' : quietColor"
      :icon="icon"
      :loading="loading"
    >
      <slot />
    </q-btn>
    <AppTooltip>{{ tooltip }}</AppTooltip>
  </span>
  <q-btn
    v-else
    :aria-label="tooltip"
    v-bind="$attrs"
    dense
    flat
    :class="{ 'app-icon-button__compact': compact, 'app-icon-button--danger': variant === 'danger-quiet', 'app-icon-button--live': live }"
    :color="live ? undefined : active ? 'positive' : quietColor"
    :icon="icon"
    :loading="loading"
  >
    <!-- What hangs off the button: a count on its corner (AppBadge). -->
    <slot />
    <AppTooltip>{{ tooltip }}</AppTooltip>
  </q-btn>
</template>

<style scoped>
/* Tight around the button: the wrapper stands in for it in whatever row it
   was dropped into, so it must take exactly the room the button takes — and
   the line it takes, which for QBtn is the middle rather than the baseline:
   in a table cell a disabled command otherwise sat above its neighbours. */
.app-icon-button {
  display: inline-flex;
  align-items: center;
  vertical-align: middle;
}
/* Sized by the kit's own numbers rather than Quasar's `xs`, which is a font
   of 8px: its icon came out 13.7px and the button 18, off every step. */
.app-icon-button__compact {
  min-width: var(--dp-control-height-compact);
  min-height: var(--dp-control-height-compact);
  padding: var(--dp-space-half);
}
.app-icon-button__compact :deep(.q-icon) {
  font-size: var(--dp-icon-sm);
}
.app-icon-button--danger:hover,
.app-icon-button--danger:focus-visible,
.app-icon-button--live {
  color: var(--dp-action-danger);
}
/* It is what the keyboard lands on, so it has to say where the keyboard is. */
.app-icon-button:focus-visible {
  outline: 2px solid var(--dp-focus-border);
  outline-offset: 2px;
  border-radius: var(--dp-radius-control);
}
</style>
