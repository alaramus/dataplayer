<script setup lang="ts">
import { AppEmptyState } from "@/shared/ui"
</script>

<template>
  <div
    class="empty-panel"
    data-testid="navigate-empty"
  >
    <AppEmptyState
      icon="account_tree"
      text="Pick a connection on the left to browse it."
    />
  </div>
</template>

<style scoped>
.empty-panel {
  padding: 12px 8px;
}
</style>
