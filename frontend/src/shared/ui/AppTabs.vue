<script setup lang="ts">
import { useAttrs } from "vue"

export interface TabOption {
  value: string
  label: string
  icon?: string
}

/**
 * The pages of one place, the one shown on a grey ground: the connection
 * window's pages, the queries panel's Favorites and History.
 *
 * Buttons that say they are pressed rather than ARIA tabs: a tab list promises
 * arrow keys and panels tied to each tab, which none of these places have.
 */
defineProps<{
  modelValue: string
  options: readonly TabOption[]
}>()

const emit = defineEmits<{ "update:modelValue": [value: string] }>()

const attrs = useAttrs()

/** A page is found the way the row is: `queries-places` → `queries-places-history`. */
function optionTestId(option: TabOption): string | undefined {
  const row = attrs["data-testid"]
  return typeof row === "string" ? `${row}-${option.value}` : undefined
}
</script>

<template>
  <div class="app-tabs">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="app-tabs__tab"
      :class="{ 'app-tabs__tab--current': option.value === modelValue }"
      :aria-pressed="option.value === modelValue"
      :data-testid="optionTestId(option)"
      @click="emit('update:modelValue', option.value)"
    >
      <q-icon
        v-if="option.icon"
        :name="option.icon"
        size="16px"
      />
      {{ option.label }}
    </button>
  </div>
</template>

<style scoped>
.app-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-1);
}

.app-tabs__tab {
  display: inline-flex;
  align-items: center;
  gap: var(--dp-space-1);
  padding: var(--dp-space-1) var(--dp-space-2);
  border: none;
  border-radius: var(--dp-radius-control);
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.app-tabs__tab--current {
  background: var(--dp-tab-current);
  font-weight: 500;
}

.app-tabs__tab:not(.app-tabs__tab--current):hover {
  background: var(--dp-hover);
}

.app-tabs__tab:focus-visible {
  outline: 2px solid var(--dp-focus-border);
  outline-offset: var(--dp-space-half);
}
</style>
