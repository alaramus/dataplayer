<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed } from "vue"

import type { AdapterTypeInfo, ServiceTemplateInfo } from "@/client"
import { adapterIcon } from "@/features/connectors/adapters"
import { useOpenGuide } from "@/features/guide/windows"
import { AppButton, AppEmptyState, AppTooltip } from "@/shared/ui"

/**
 * What one source type is, beside the grid rather than over it.
 *
 * Not a dialog: the grid stays visible, so several types can be read through
 * in a row before one is chosen. This is the reason the catalog exists — a
 * tile that led straight to the form would be a dropdown, enlarged.
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
const openGuide = useOpenGuide()

/**
 * The two short lists at the head of the type's page in the guide, as the
 * server read them from it (D183). The driver's own capabilities are what a
 * screen switches on; these are what a person reads before choosing.
 */
const groups = computed(() =>
  [
    { id: "see", title: "What you can see", icon: appIcons.visibility, items: props.type?.can_see ?? [] },
    { id: "change", title: "What you can change", icon: appIcons.edit, items: props.type?.can_change ?? [] },
  ].filter((group) => group.items.length > 0)
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
        size="var(--dp-icon-xl)"
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

      <section
        v-for="group in groups"
        :key="group.id"
        class="adapter-panel__group"
        :data-testid="`adapter-can-${group.id}`"
      >
        <h3 class="adapter-panel__group-title dp-overline">
          <q-icon
            :name="group.icon"
            size="var(--dp-icon-sm)"
          />
          <span>{{ group.title }}</span>
        </h3>
        <ul class="adapter-panel__list">
          <li
            v-for="item in group.items"
            :key="item"
          >
            {{ item }}
          </li>
        </ul>
      </section>

      <!-- A source that only connects: it has nothing to browse and nothing
           to read, and saying so is more use than an empty panel. -->
      <AppEmptyState
        v-if="groups.length === 0"
        icon="help"
        text="This type only checks that it can reach the source."
      />
    </div>

    <q-separator />

    <div class="adapter-panel__foot">
      <!-- Offered only where this server has a template for the type, and
           disabled with the server's own reason where it has one and cannot
           use it: a button that would be refused is worse than no button.
           What it runs, or why it cannot, is said on hover: written under
           each button, it pushed the short lists out of the panel. The
           tooltip hangs off the wrapper, because a disabled button takes no
           pointer events. -->
      <div
        v-for="offer in offers"
        :key="offer.key"
        class="adapter-panel__start"
        :data-testid="`start-service-offer-${offer.key}`"
      >
        <AppButton
          variant="secondary"
          :label="`Start ${offer.title} here`"
          :disable="!offer.available"
          :data-testid="`start-service-${offer.key}`"
          @click="emit('start', offer)"
        />
        <AppTooltip>
          {{
            offer.available
              ? `Runs ${offer.image} on this server and saves the connection for you.`
              : offer.unavailable_reason ?? "This server cannot start it"
          }}
        </AppTooltip>
      </div>
      <div class="adapter-panel__commands">
        <AppButton
          variant="secondary"
          :icon="appIcons.menuBook"
          label="Guide"
          data-testid="adapter-guide"
          @click="openGuide(type.guide)"
        />
        <AppButton
          class="adapter-panel__create"
          label="Create connection"
          data-testid="create-from-catalog"
          @click="emit('create')"
        />
      </div>
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
  font-size: var(--dp-font-size-lg);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.adapter-panel__category {
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
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
  margin: 0;
}
.adapter-panel__list {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  margin: 0;
  padding-left: var(--dp-space-4);
  line-height: 1.4;
}
.adapter-panel__commands {
  display: flex;
  gap: var(--dp-space-2);
}
.adapter-panel__create {
  flex: 1;
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
