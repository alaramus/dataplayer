<script setup lang="ts">
import { AppButton, AppSelect } from "@/shared/ui"

import { PAGE_SIZES } from "./types"
import type { PageSize } from "./types"

defineProps<{ pageSize: PageSize }>()
const emit = defineEmits<{ "update:pageSize": [value: PageSize] }>()
const pageSizeOptions = PAGE_SIZES.map((size) => ({ label: String(size), value: size }))

function selectPageSize(value: unknown) {
  if (typeof value === "number" && PAGE_SIZES.some((size) => size === value)) {
    emit("update:pageSize", value as PageSize)
  }
}
</script>

<template>
  <div
    class="grid-header"
    data-testid="grid-header"
  >
    <div class="grid-header__commands">
      <AppButton
        label="Filters"
        variant="quiet"
        size="sm"
        disable
      />
      <AppButton
        label="Sort"
        variant="quiet"
        size="sm"
        disable
      />
      <AppButton
        label="Columns"
        variant="quiet"
        size="sm"
        disable
      />
      <AppButton
        label="Pin"
        variant="quiet"
        size="sm"
        disable
      />
      <AppButton
        label="Copy"
        variant="quiet"
        size="sm"
        disable
      />
    </div>

    <AppSelect
      :model-value="pageSize"
      :options="pageSizeOptions"
      label="Rows"
      compact
      class="grid-header__page-size"
      data-testid="grid-page-size"
      @update:model-value="selectPageSize"
    />
  </div>
</template>

<style scoped>
.grid-header {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  min-height: 44px;
  gap: 8px;
  border-bottom: 1px solid var(--dp-border);
  overflow-x: auto;
}

.grid-header__commands {
  display: flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}

.grid-header__page-size {
  width: 88px;
  flex: none;
}
</style>
