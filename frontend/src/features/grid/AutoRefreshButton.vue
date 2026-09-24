<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import { AppButton, AppMenu, AppTooltip } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

import {
  REFRESH_SECONDS,
  refreshItemName,
  refreshLabel,
  refreshSecondsOf,
  refreshTooltip,
} from "./autoRefresh"
import type { RefreshSeconds } from "./autoRefresh"

/**
 * How often this grid re-reads itself, chosen from a menu.
 *
 * The interval is on the button rather than only in the tooltip. A grid that
 * refetches by itself and looks exactly like one that does not is a grid
 * whose rows move for no visible reason; the label is what makes the polling
 * something the user can see they asked for, and turn off.
 */
const props = defineProps<{
  seconds: RefreshSeconds | null
  /** Why it is not refreshing at this moment, from `refreshHeldBy`. */
  held?: string | null
  /** Nothing has been read yet, so there is nothing to re-read. */
  disable?: boolean
  /** The owning view's test hook; defaults to the grid's established one. */
  testId?: string
}>()

const emit = defineEmits<{ "update:seconds": [value: RefreshSeconds | null] }>()

const items = computed<MenuItem[]>(() => [
  {
    name: refreshItemName(null),
    label: "Off",
    // A tick rather than a highlight: the kit's menu has one way to say
    // "this is the one", and it is the icon slot.
    ...(props.seconds === null ? { icon: appIcons.check } : {}),
  },
  ...REFRESH_SECONDS.map((seconds) => ({
    name: refreshItemName(seconds),
    label: refreshLabel(seconds),
    ...(props.seconds === seconds ? { icon: appIcons.check } : {}),
  })),
])

const tooltip = computed(() => refreshTooltip(props.seconds, props.held ?? null))

function pick(name: string) {
  const chosen = refreshSecondsOf(name)
  if (chosen === undefined) return
  emit("update:seconds", chosen)
}
</script>

<template>
  <!-- The drawn label is an interval, and off it is nothing at all: neither
       names the command, so the name is spoken rather than drawn (U04). -->
  <AppButton
    :variant="seconds === null ? 'quiet' : 'secondary'"
    size="sm"
    :icon="appIcons.autorenew"
    :label="seconds === null ? undefined : refreshLabel(seconds)"
    :aria-label="tooltip"
    layout="toolbar"
    :disable="disable"
    :data-testid="testId ?? 'grid-auto-refresh'"
    :data-refresh="seconds === null ? 'off' : String(seconds)"
  >
    <AppTooltip>{{ tooltip }}</AppTooltip>
    <AppMenu
      :items="items"
      @select="pick"
    />
  </AppButton>
</template>

