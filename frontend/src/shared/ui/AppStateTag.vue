<script setup lang="ts">
import { computed } from "vue"

import { stateTone, toneFill, toneText } from "./tokens"
import type { StateTone } from "./tokens"

const props = withDefaults(
  defineProps<{
    /** The source's word for the state, already in the reader's language. */
    label: string
    tone?: StateTone
  }>(),
  { tone: "neutral" }
)

/**
 * A dot in the tone and the word beside it, in the tone too. Not a badge: a
 * state sits in a line of text — a header, a field — and a filled ground
 * there was the loudest thing on the page for a container that was merely
 * running.
 */
const message = computed(() => stateTone(props.tone))
</script>

<template>
  <span
    class="app-state-tag"
    :class="message === null ? 'app-state-tag--neutral' : toneText(message)"
    :data-tone="tone"
  >
    <span
      class="app-state-tag__dot"
      :class="message === null ? 'app-state-tag__dot--neutral' : toneFill(message)"
      aria-hidden="true"
    />
    {{ label }}
  </span>
</template>

<style scoped>
.app-state-tag {
  display: inline-flex;
  align-items: center;
  gap: var(--dp-space-1);
  font-weight: 500;
}
.app-state-tag--neutral {
  color: var(--dp-text-muted);
}
.app-state-tag__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.app-state-tag__dot--neutral {
  background: var(--dp-text-muted);
}
</style>
