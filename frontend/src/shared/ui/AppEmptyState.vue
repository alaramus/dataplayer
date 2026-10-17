<script setup lang="ts">
withDefaults(defineProps<{ text: string; icon?: string; inset?: boolean }>(), {
  icon: undefined,
  inset: false,
})
</script>

<template>
  <div
    class="app-empty-state"
    :class="{ 'app-empty-state--inset': inset }"
  >
    <q-icon
      v-if="icon"
      :name="icon"
      size="var(--dp-icon-md)"
    />
    <span>{{ text }}</span>
  </div>
</template>

<style scoped>
/* A gap rather than Quasar's q-gutter, whose negative top margin stood the
   line flush against whatever was above it. */
.app-empty-state {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  color: var(--dp-text-muted);
}
/* Standing alone in a tool's body with nothing around it to set its place:
   the inset that tool's list has, so Services, Queries and Search index say
   "nothing here" from the same spot. A side list pads its own, 8px. */
.app-empty-state--inset {
  padding: var(--dp-space-2) var(--dp-space-3);
}
</style>
