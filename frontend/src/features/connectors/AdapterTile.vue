<script setup lang="ts">
import type { AdapterTypeInfo } from "@/client"
import { adapterIcon } from "@/features/connectors/adapters"

/**
 * One source type in the catalog's grid.
 *
 * Three things: the logo, the name, and what sort of source it is. The old
 * application put capability chips here too and took them out again — a tile
 * is scanned, and the panel beside it is what is read.
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
        size="24px"
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
  gap: 4px;
  min-width: 0;
  padding: 8px;
  border: 1px solid rgba(128, 128, 128, 0.3);
  border-radius: 4px;
  cursor: pointer;
}
.adapter-tile:hover,
.adapter-tile:focus-visible {
  border-color: var(--q-primary);
}
.adapter-tile--selected {
  border-color: var(--q-primary);
  box-shadow: inset 0 0 0 1px var(--q-primary);
}
.adapter-tile__head {
  display: flex;
  align-items: center;
  gap: 6px;
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
  font-size: 11px;
  opacity: 0.6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
