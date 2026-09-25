<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { appIcons } from "@/shared/ui"

import { dropOnPair, pairTargetLabel } from "./pairs"
import type { PairsApi } from "./usePairs"

/**
 * The Pair target in the header, beside Open in a window, while a catalog tab
 * is carried (D167). Draws nothing for any other tab.
 */
const props = defineProps<{ pairs: PairsApi; panelId: string | null }>()
const hovered = ref(false)

const carried = computed(() =>
  props.panelId === null ? null : props.pairs.candidateOf(props.panelId)
)
const refused = computed(() =>
  carried.value !== null && dropOnPair(props.pairs.waiting.value, carried.value).kind === "refuse"
)
const label = computed(() =>
  carried.value === null ? "" : pairTargetLabel(props.pairs.waiting.value, carried.value)
)
watch(carried, (value) => { if (value === null) hovered.value = false })

function release() {
  hovered.value = false
  if (props.panelId !== null && !refused.value) props.pairs.drop(props.panelId)
}
</script>

<template>
  <div
    v-if="carried"
    class="pair-target"
    :class="{
      'pair-target--hovered': hovered && !refused,
      'pair-target--refused': refused,
    }"
    data-testid="workspace-pair-target"
    role="status"
    @pointerenter="hovered = true"
    @pointerleave="hovered = false"
    @pointerup="release"
  >
    <q-icon
      :name="appIcons.pair"
      size="28px"
    />
    <span>{{ label }}</span>
  </div>
</template>

<style scoped>
/* The detach target's look, because it is the same kind of place. */
.pair-target {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--dp-space-2);
  border: 2px dashed var(--dp-dropzone-border);
  background: var(--dp-chrome-raised);
  color: var(--dp-text-strong);
}
.pair-target--hovered {
  border-style: solid;
  background: var(--dp-dropzone);
}
.pair-target--refused {
  border-color: var(--dp-border);
  color: var(--dp-text-muted);
}
</style>
