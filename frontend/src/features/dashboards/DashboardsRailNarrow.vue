<script setup lang="ts">
import type { DashboardPublic } from "@/client"
import { AppIconButton } from "@/shared/ui"
import { panelColorStyle } from "@/shared/ui/panelColor"

import { railEntry } from "./railEntry"

/**
 * The dashboards rail pushed aside to forty pixels, the way the column of
 * connections is (D12): the names go, a dashboard is its icon and its tooltip,
 * and what the wide rail can start — a new dashboard, the Sources window, the
 * store — is still one press away.
 */
defineProps<{
  own: readonly DashboardPublic[]
  shared: readonly DashboardPublic[]
  currentId: string | null
  maySetUp: boolean
  creating: boolean
}>()

const emit = defineEmits<{
  expand: []
  create: []
  select: [dashboardId: string]
  sources: []
  store: []
}>()
</script>

<template>
  <div
    class="rail-narrow"
    data-testid="dashboards-rail-narrow"
  >
    <AppIconButton
      icon="chevron_right"
      tooltip="Show Dashboards"
      data-testid="dashboards-expand"
      @click="emit('expand')"
    />
    <AppIconButton
      icon="add"
      tooltip="New dashboard"
      :loading="creating"
      data-testid="dashboard-new"
      @click="emit('create')"
    />
    <!-- A rule stands between two groups that both show something: with no
         dashboards, or only shared ones, a rule on each side of nothing is
         two lines in a row. -->
    <q-separator
      class="rail-narrow__rule"
      data-testid="rail-narrow-rule"
    />

    <div
      v-for="dashboard in own"
      :key="dashboard.id"
      class="rail-narrow__slot"
      :class="{
        'rail-narrow__slot--selected': railEntry(dashboard.color, dashboard.id === currentId).variant === 'secondary',
        'rail-narrow__slot--tinted': railEntry(dashboard.color, dashboard.id === currentId).tinted,
        'rail-narrow__slot--filled': railEntry(dashboard.color, dashboard.id === currentId).filled,
      }"
      :style="panelColorStyle(dashboard.color)"
    >
      <AppIconButton
        icon="dashboard"
        :tooltip="dashboard.name"
        :data-testid="`dashboard-narrow-${dashboard.name}`"
        @click="emit('select', dashboard.id)"
      />
    </div>
    <q-separator
      v-if="own.length > 0 && shared.length > 0"
      class="rail-narrow__rule"
      data-testid="rail-narrow-rule"
    />
    <div
      v-for="dashboard in shared"
      :key="dashboard.id"
      class="rail-narrow__slot"
      :class="{
        'rail-narrow__slot--selected': railEntry(dashboard.color, dashboard.id === currentId).variant === 'secondary',
        'rail-narrow__slot--tinted': railEntry(dashboard.color, dashboard.id === currentId).tinted,
        'rail-narrow__slot--filled': railEntry(dashboard.color, dashboard.id === currentId).filled,
      }"
      :style="panelColorStyle(dashboard.color)"
    >
      <AppIconButton
        icon="group"
        :tooltip="`${dashboard.name}, shared by ${dashboard.owner ?? 'somebody'}`"
        :data-testid="`dashboard-narrow-${dashboard.name}`"
        @click="emit('select', dashboard.id)"
      />
    </div>

    <q-separator
      v-if="own.length + shared.length > 0"
      class="rail-narrow__rule"
      data-testid="rail-narrow-rule"
    />
    <AppIconButton
      icon="sensors"
      tooltip="Sources"
      data-testid="agents-open"
      @click="emit('sources')"
    />
    <AppIconButton
      v-if="maySetUp"
      icon="storage"
      tooltip="The metrics store"
      data-testid="store-open"
      @click="emit('store')"
    />
  </div>
</template>

<style scoped>
.rail-narrow {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 0;
  padding: 2px 0;
  overflow-x: hidden;
  overflow-y: auto;
}

.rail-narrow__rule {
  align-self: stretch;
  margin: 2px 8px 4px;
}

.rail-narrow__slot {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}

/* The blue the wide rail writes the open dashboard in: the icon is what is
   left of that entry, so it carries the mark. A plain fill, as the column of
   connections draws, is the colour of the card itself in the dark theme. */
.rail-narrow__slot--selected {
  color: var(--dp-action-secondary);
}

/* A dashboard's own colour, as in the wide rail (railEntry.ts). */
.rail-narrow__slot--tinted {
  background: var(--dp-panel-quiet);
}

.rail-narrow__slot--filled {
  background: var(--dp-panel-background);
  color: var(--dp-panel-foreground);
}
</style>
