<script setup lang="ts">
withDefaults(defineProps<{ text: string; icon?: string }>(), { icon: undefined })
</script>

<template>
  <div class="app-empty-state row items-center q-gutter-sm">
    <q-icon
      v-if="icon"
      :name="icon"
      size="var(--dp-icon-md)"
    />
    <span>{{ text }}</span>
  </div>
</template>

<style scoped>
.app-empty-state {
  color: var(--dp-text-muted);
}
</style>
