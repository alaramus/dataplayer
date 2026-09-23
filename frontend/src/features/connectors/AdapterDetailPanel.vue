<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import type { AdapterTypeInfo, Capability, ServiceTemplateInfo } from "@/client"
import { adapterIcon } from "@/features/connectors/adapters"
import { AppBadge, AppButton, AppEmptyState, AppTooltip } from "@/shared/ui"

/**
 * What one source type is, beside the grid rather than over it.
 *
 * Not a dialog: the grid stays visible, so several types can be read through
 * in a row before one is chosen. This is the reason the catalog exists — a
 * tile that led straight to the form would be the old dropdown, enlarged.
 */
const props = defineProps<{
  type: AdapterTypeInfo | null
  /**
   * The services of this kind this server could start, if any.
   *
   * A source type does not know whether a container of it can be started
   * here: that is a question about this machine, and the answer arrives with
   * the templates (D82). The panel is told rather than asking, so nothing
   * here decides what may be offered.
   *
   * Several, because one source type can be started in more than one way: a
   * PostgreSQL and a PostgreSQL with TimescaleDB in it are the same kind of
   * connection and different things to run (D119). Offered as one button each
   * rather than a choice inside the dialog, so that what this machine can
   * start is visible before anything is pressed.
   */
  templates?: ServiceTemplateInfo[]
}>()

const emit = defineEmits<{ create: []; start: [template: ServiceTemplateInfo] }>()

const offers = computed(() => props.templates ?? [])

/**
 * The two things a capability can be a statement about.
 *
 * The server answers a group per capability; the wording of the heading is a
 * caption on this screen, so it lives here.
 */
const GROUPS = [
  { id: "explore", title: "What you can see", icon: appIcons.visibility },
  { id: "manage", title: "What you can change", icon: appIcons.edit },
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
      <!-- Offered only where this server has a template for the type, and
           disabled with the server's own reason where it has one and cannot
           use it: a button that would be refused is worse than no button. -->
      <div
        v-for="offer in offers"
        :key="offer.key"
        class="adapter-panel__start"
      >
        <AppButton
          variant="secondary"
          :label="`Start ${offer.title} here`"
          :disable="!offer.available"
          :data-testid="`start-service-${offer.key}`"
          @click="emit('start', offer)"
        />
        <AppTooltip
          v-if="offer.unavailable_reason"
          :text="offer.unavailable_reason"
        />
        <span
          v-if="offer.available"
          class="adapter-panel__hint"
        >
          Runs {{ offer.image }} on this server and saves the connection
          for you.
        </span>
        <span
          v-else
          class="adapter-panel__hint"
          :data-testid="`start-service-reason-${offer.key}`"
        >
          {{ offer.unavailable_reason }}
        </span>
      </div>
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
  min-width: 0;
  width: clamp(240px, 32%, 320px);
  flex: 0 1 auto;
  border-left: 1px solid var(--dp-border);
}
.adapter-panel__start {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}
.adapter-panel__hint {
  font-size: 11px;
  color: var(--dp-text-muted);
}
.adapter-panel--empty {
  justify-content: center;
  padding: var(--dp-space-3);
}
.adapter-panel__head {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-3);
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
  gap: var(--dp-space-4);
  padding: var(--dp-space-3);
}
.adapter-panel__description {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
}
.adapter-panel__group {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  min-width: 0;
}
.adapter-panel__group-title {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
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
  gap: var(--dp-space-1);
  min-width: 0;
}
.adapter-panel__foot {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-3);
}
</style>
