<script setup lang="ts">
import { computed } from "vue"

import type { AdapterTypeInfo, Capability } from "@/client"
import { adapterIcon } from "@/features/connectors/adapters"
import { AppBadge, AppButton, AppEmptyState } from "@/shared/ui"

/**
 * What one source type is, beside the grid rather than over it.
 *
 * Not a dialog: the grid stays visible, so several types can be read through
 * in a row before one is chosen. This is the reason the catalog exists — a
 * tile that led straight to the form would be the old dropdown, enlarged.
 */
const props = defineProps<{ type: AdapterTypeInfo | null }>()

const emit = defineEmits<{ create: [] }>()

/**
 * The two things a capability can be a statement about.
 *
 * The server answers a group per capability; the wording of the heading is a
 * caption on this screen, so it lives here.
 */
const GROUPS = [
  { id: "explore", title: "What you can see", icon: "visibility" },
  { id: "manage", title: "What you can change", icon: "edit" },
] as const

const groups = computed(() =>
  GROUPS.map((group) => ({
    ...group,
    items: (props.type?.capabilities ?? []).filter(
      (capability: Capability) => capability.group === group.id
    ),
  })).filter((group) => group.items.length > 0)
)
</script>

<template>
  <div
    v-if="type"
    class="adapter-panel"
    data-testid="adapter-panel"
  >
    <div class="adapter-panel__head">
      <q-icon
        :name="adapterIcon(type.name)"
        size="32px"
      />
      <div class="adapter-panel__title">
        <span class="adapter-panel__name">{{ type.title }}</span>
        <span class="adapter-panel__category">{{ type.category_title }}</span>
      </div>
    </div>

    <q-separator />

    <div class="adapter-panel__body">
      <p class="adapter-panel__description">
        {{ type.description }}
      </p>

      <div
        v-for="group in groups"
        :key="group.id"
        class="adapter-panel__group"
      >
        <div class="adapter-panel__group-title">
          <q-icon
            :name="group.icon"
            size="14px"
          />
          <span>{{ group.title }}</span>
        </div>
        <div class="adapter-panel__chips">
          <AppBadge
            v-for="item in group.items"
            :key="item.title"
            :label="item.title"
          />
        </div>
      </div>

      <!-- A source that only connects: it has nothing to browse and nothing
           to read, and saying so is more use than an empty panel. -->
      <AppEmptyState
        v-if="groups.length === 0"
        icon="help_outline"
        text="This type only checks that it can reach the source."
      />
    </div>

    <q-separator />

    <div class="adapter-panel__foot">
      <AppButton
        label="Create connection"
        data-testid="create-from-catalog"
        @click="emit('create')"
      />
    </div>
  </div>

  <div
    v-else
    class="adapter-panel adapter-panel--empty"
  >
    <AppEmptyState
      icon="touch_app"
      text="Pick a source type to see what it can do."
    />
  </div>
</template>

<style scoped>
.adapter-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  width: clamp(240px, 32%, 320px);
  flex: none;
  border-left: 1px solid var(--dp-border);
}
.adapter-panel--empty {
  justify-content: center;
  padding: 12px;
}
.adapter-panel__head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  min-width: 0;
}
.adapter-panel__title {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.adapter-panel__name {
  font-size: 17px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.adapter-panel__category {
  font-size: 12px;
  opacity: 0.6;
}
/* One scrollbar, on the right — never along the bottom. */
.adapter-panel__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 12px;
}
.adapter-panel__description {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
}
.adapter-panel__group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.adapter-panel__group-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  opacity: 0.7;
}
/* The one place wrapping is wanted: a row of labels of unequal length. */
.adapter-panel__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}
.adapter-panel__foot {
  flex: none;
  display: flex;
  justify-content: flex-end;
  padding: 8px 12px;
}
</style>
