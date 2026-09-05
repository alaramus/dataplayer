<script setup lang="ts">
import { computed } from "vue"

import { AppButton, AppTooltip } from "@/shared/ui"

import { freshnessLabel, freshnessTooltip, isLive } from "./freshness"
import type { Freshness } from "./freshness"
import { useNow } from "./useNow"

/**
 * Whether what is on screen was read now or kept, and how old it is.
 *
 * Beside the reload it explains, and it is the reload: the answer to "is this
 * stale?" and the way to do something about it are one control, because a
 * badge that only reports leaves somebody hunting for the button (D105).
 *
 * The age counts up on its own. A label frozen at the moment the page
 * arrived would say "1s" for an hour, which is worse than saying nothing.
 */
const props = defineProps<{
  freshness: Freshness | undefined
  /** What this connection was told to keep, when its owner chose (D105). */
  cacheTtlSeconds?: number | null
  /** A read is under way, so the badge is about to be about something else. */
  loading?: boolean
  /**
   * How a test addresses this one. Two can be on screen at once — a level and
   * the rows opened out of it — and they are about different readings.
   */
  testid?: string
}>()

const emit = defineEmits<{ reload: [] }>()

const now = useNow()
const live = computed(
  () => props.freshness !== undefined && isLive(props.freshness, now.value)
)
const label = computed(() =>
  props.freshness === undefined ? "" : freshnessLabel(props.freshness, now.value)
)
const tooltip = computed(() =>
  props.freshness === undefined
    ? ""
    : freshnessTooltip(props.freshness, props.cacheTtlSeconds, now.value)
)
</script>

<template>
  <AppButton
    v-if="freshness !== undefined"
    :variant="live ? 'secondary' : 'quiet'"
    size="sm"
    icon="schedule"
    :label="label"
    :loading="loading === true"
    class="freshness"
    :data-testid="testid ?? 'freshness'"
    :data-live="live ? 'yes' : 'no'"
    @click="emit('reload')"
  >
    <AppTooltip>{{ tooltip }}</AppTooltip>
  </AppButton>
</template>

<style scoped>
/* The icon and the age on one line, the way the auto-refresh button wears
   its interval: stacked, one control reads as two. */
.freshness :deep(.q-btn__content) {
  flex-wrap: nowrap;
  gap: 4px;
}
</style>
