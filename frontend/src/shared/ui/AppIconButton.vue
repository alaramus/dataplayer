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

// The wrapper below would otherwise take data-testid and aria-label off the
// button they name.
defineOptions({ inheritAttrs: false })
</script>

<template>
  <!--
    Two shapes of the same button, because a disabled one takes no pointer
    events: a tooltip hung on it never opens, and the reason a command is off
    is exactly what a disabled button has to be able to say. So that one hangs
    off a wrapper instead — the answer the command bar already gives (D69),
    moved into the kit so no screen has to know about it.

    Only the disabled shape is wrapped. The wrapper is a box in the layout, and
    the enabled button is in a hundred places that were laid out around it.
  -->
  <span
    v-if="disable"
    class="app-icon-button"
  >
    <q-btn
      v-bind="$attrs"
      dense
      flat
      disable
      :size="compact ? 'xs' : undefined"
      :color="look.color"
      :icon="icon"
      :loading="loading"
    />
    <AppTooltip>{{ tooltip }}</AppTooltip>
  </span>
  <q-btn
    v-else
    v-bind="$attrs"
    dense
    flat
    :size="compact ? 'xs' : undefined"
    :color="look.color"
    :icon="icon"
    :loading="loading"
  >
    <AppTooltip>{{ tooltip }}</AppTooltip>
  </q-btn>
</template>

<style scoped>
/* Tight around the button: the wrapper stands in for it in whatever row it
   was dropped into, so it must take exactly the room the button takes. */
.app-icon-button {
  display: inline-flex;
  align-items: center;
}
</style>
