<script setup lang="ts">
import { AppEmptyState } from "@/shared/ui"
</script>

<template>
  <div
    class="empty-panel"
    data-testid="work-empty"
  >
    <AppEmptyState
      icon="table_chart"
      text="Pick a table or a file in the catalog to read it here."
    />
  </div>
</template>

<style scoped>
.empty-panel {
  padding: 12px 8px;
}
</style>
