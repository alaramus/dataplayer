<script setup lang="ts">
import type { AdapterTypeInfo } from "@/client"
import { adapterIcon } from "@/features/connectors/adapters"

/**
 * One source type in the catalog's grid.
 *
 * Three things: the logo, the name, and what sort of source it is. No
 * capability chips: a tile is scanned, and the panel beside it is what is read.
 */
defineProps<{ type: AdapterTypeInfo; selected: boolean }>()

const emit = defineEmits<{ pick: []; open: [] }>()
</script>

<template>
  <div
    role="button"
    tabindex="0"
    class="adapter-tile"
    :class="{ 'adapter-tile--selected': selected }"
    :data-testid="`adapter-${type.name}`"
    @click="emit('pick')"
    @dblclick="emit('open')"
    @keydown.enter="emit('open')"
    @keydown.space.prevent="emit('pick')"
  >
    <div class="adapter-tile__head">
      <q-icon
        :name="adapterIcon(type.name)"
        size="var(--dp-icon-lg)"
      />
      <span class="adapter-tile__name">{{ type.title }}</span>
    </div>

    <span class="adapter-tile__category">{{ type.category_title }}</span>
  </div>
</template>

<style scoped>
.adapter-tile {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  min-width: 0;
  padding: var(--dp-space-2);
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
  cursor: pointer;
}
/* Grey, as a chosen row is everywhere else in the application. */
.adapter-tile:hover {
  background: var(--dp-hover);
}
.adapter-tile:focus-visible {
  outline: 2px solid var(--dp-focus-border);
  outline-offset: calc(-1 * var(--dp-space-half));
}
/* Pointed at, the chosen tile stays chosen: :hover alone outranks a class. */
.adapter-tile--selected,
.adapter-tile--selected:hover {
  border-color: var(--dp-focus-border);
  background: var(--dp-active);
}
.adapter-tile__head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  min-width: 0;
}
.adapter-tile__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.adapter-tile__category {
  font-size: var(--dp-font-size-xs);
  line-height: var(--dp-line-height-sm);
  color: var(--dp-text-muted);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
</style>
