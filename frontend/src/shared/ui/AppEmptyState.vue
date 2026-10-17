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
/* Standing alone in a panel's body with nothing around it to set its place:
   the inset a tool's list has, so the Services, Queries, Search index and
   chats panels say "nothing here" from the same spot. */
.app-empty-state--inset {
  padding: var(--dp-space-2) var(--dp-space-3);
}
</style>
