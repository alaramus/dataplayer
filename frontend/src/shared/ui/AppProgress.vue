<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(defineProps<{
  label: string
  /** A fraction of measured work, or null when its size is unknown. */
  value?: number | null
  paused?: boolean
}>(), { value: null, paused: false })

const fraction = computed(() => props.value === null ? null : Math.min(1, Math.max(0, props.value)))
</script>

<template>
  <div
    class="app-progress"
    :class="{ 'app-progress--unknown': fraction === null, 'app-progress--paused': paused }"
    role="progressbar"
    :aria-label="label"
    :aria-valuemin="0"
    :aria-valuemax="100"
    :aria-valuenow="fraction === null ? undefined : Math.round(fraction * 100)"
    :aria-valuetext="paused ? 'Paused' : undefined"
  >
    <span
      class="app-progress__fill"
      :style="{ width: fraction === null ? '35%' : `${fraction * 100}%` }"
    />
  </div>
</template>

<style scoped>
.app-progress {
  height: 4px;
  width: 100%;
  overflow: hidden;
  border-radius: 2px;
  background: var(--dp-border);
}
.app-progress__fill {
  display: block;
  height: 100%;
  background: var(--q-primary);
  transition: width 150ms ease;
}
.app-progress--unknown .app-progress__fill {
  animation: progress-travel 1.3s ease-in-out infinite alternate;
}
.app-progress--paused .app-progress__fill {
  animation-play-state: paused;
  opacity: 0.6;
}
@keyframes progress-travel {
  from { transform: translateX(0); }
  to { transform: translateX(190%); }
}
@media (prefers-reduced-motion: reduce) {
  .app-progress__fill { animation: none !important; transition: none; }
}
</style>
