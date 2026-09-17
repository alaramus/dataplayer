<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"

import { messageOf } from "@/shared/api/errors"
import { serverStorageKey } from "@/shared/servers/context"
import { AppButton, AppEmptyState, AppIconButton, AppSpinner, AppTooltip, AppTree, useToast } from "@/shared/ui"
import { panelColorStyle } from "@/shared/ui/panelColor"
import { WorkspaceSeparator } from "@/shared/workspace"

import AgentsDialog from "./AgentsDialog.vue"
import {
  useCreateDashboard,
  useDashboards,
  useLivePoints,
  useMetricsCatalog,
  useStoreJobEvents,
  useStoreStatus,
} from "./api"
import { catalogTree, indexCatalog } from "./catalog"
import DashboardView from "./DashboardView.vue"
import { takeDashboardIntent } from "./intent"
import DashboardsRailNarrow from "./DashboardsRailNarrow.vue"
import { railEntry } from "./railEntry"
import { clampRailWidth, parseRailNarrow, parseRailWidth, RAIL_NARROW_PX } from "./railWidth"
import { splitByOwner } from "./sharing"
import StoreDialog from "./StoreDialog.vue"
import StoreSetup from "./StoreSetup.vue"

/**
 * The dashboards card: what takes the room of the workspace sections (D125).
 * The dashboards and the sources on the left, the open dashboard on the right,
 * and before any of that, the store to draw from (D126).
 */
const toast = useToast()
const status = useStoreStatus()
useStoreJobEvents()
useLivePoints()

const ready = computed(() => status.data.value?.state === "ready")
const dashboards = useDashboards(ready)
const catalog = useMetricsCatalog(ready)
const creating = useCreateDashboard()
const index = computed(() => indexCatalog(catalog.data.value))
const sources = computed(() => catalogTree(catalog.data.value))
const sourcesExpanded = ref<string[]>([])
const agentsOpen = ref(false)
const storeOpen = ref(false)

const SELECTED_KEY = "dataplayer-dashboard"

function storedSelection(): string | null {
  try {
    return localStorage.getItem(serverStorageKey(SELECTED_KEY))
  } catch {
    return null
  }
}

// A link followed here names the dashboard to open, over the one last open.
const asked = takeDashboardIntent()
const selectedId = ref<string | null>(asked ?? storedSelection())
const current = computed(() => {
  const list = dashboards.data.value ?? []
  return list.find((one) => one.id === selectedId.value) ?? list[0] ?? null
})
const listed = computed(() => splitByOwner(dashboards.data.value ?? []))

// Said once, when the list first arrives: the same words for a dashboard that
// is gone and one nobody shared, as the server gives (D33).
if (asked !== null) {
  const stop = watch(
    () => dashboards.data.value,
    (list) => {
      if (list === undefined) return
      if (!list.some((one) => one.id === asked)) {
        toast.error("That dashboard does not exist, or it has not been shared with you")
      }
      stop()
    },
    { immediate: true }
  )
}

watch(current, (dashboard) => {
  try {
    if (dashboard !== null) localStorage.setItem(serverStorageKey(SELECTED_KEY), dashboard.id)
  } catch {
    // Remembering which one was open is a courtesy.
  }
})

async function createDashboard() {
  const count = (dashboards.data.value ?? []).length
  try {
    const created = await creating.mutateAsync(count === 0 ? "My dashboard" : `Dashboard ${String(count + 1)}`)
    selectedId.value = created.id
  } catch (cause) {
    toast.error(messageOf(cause, "The dashboard could not be created"))
  }
}

function afterDelete() {
  selectedId.value = null
}

const RAIL_WIDTH_KEY = "dataplayer-dashboards-rail"
const RAIL_NARROW_KEY = "dataplayer-dashboards-rail-narrow"

function stored(key: string): string | null {
  try {
    return localStorage.getItem(serverStorageKey(key))
  } catch {
    return null
  }
}

function store(key: string, value: string) {
  try {
    localStorage.setItem(serverStorageKey(key), value)
  } catch {
    // Like the dashboard last open: a courtesy, not state.
  }
}

const spaceElement = ref<HTMLElement | null>(null)
const spaceWidth = ref(0)
const railWidth = ref(parseRailWidth(stored(RAIL_WIDTH_KEY)))
const railNarrow = ref(parseRailNarrow(stored(RAIL_NARROW_KEY)))
// Held to the space it is drawn in, so a window made narrower narrows the
// rail too; what is stored is what was dragged to. Pushed aside, it keeps that
// width for when it comes back.
const shownRailWidth = computed(() =>
  railNarrow.value ? RAIL_NARROW_PX : clampRailWidth(railWidth.value, spaceWidth.value)
)

const observer = new ResizeObserver((entries) => {
  const entry = entries[0]
  if (entry !== undefined) spaceWidth.value = entry.contentRect.width
})
onMounted(() => {
  if (spaceElement.value !== null) observer.observe(spaceElement.value)
})
onBeforeUnmount(() => {
  observer.disconnect()
})

function resizeRail(deltaPx: number) {
  if (railNarrow.value) return
  railWidth.value = clampRailWidth(shownRailWidth.value + deltaPx, spaceWidth.value)
}

// A press on the gap beside a pushed-aside rail brings it back, as the
// border of a collapsed workspace column does.
function pressGap() {
  if (railNarrow.value) railNarrow.value = false
}

watch(railWidth, (width) => {
  store(RAIL_WIDTH_KEY, String(width))
})
watch(railNarrow, (narrow) => {
  store(RAIL_NARROW_KEY, narrow ? "narrow" : "wide")
})

// The header button collapses the first panel of the space being shown
// through one shape; here that is the dashboards rail.
defineExpose({
  toggleFirstPanel: () => { railNarrow.value = !railNarrow.value },
  firstPanelCollapsed: computed(() => railNarrow.value),
})
</script>

<template>
  <div
    ref="spaceElement"
    class="dashboards"
    data-testid="dashboards-space"
  >
    <div
      v-if="status.isPending.value"
      class="dashboards__card dashboards__card--main dashboards__center"
    >
      <AppSpinner />
    </div>

    <div
      v-else-if="status.isError.value"
      class="dashboards__card dashboards__card--main dashboards__center"
    >
      <AppEmptyState
        icon="error_outline"
        :text="messageOf(status.error.value, 'Dashboards could not be read')"
      />
    </div>

    <div
      v-else-if="status.data.value && !ready"
      class="dashboards__card dashboards__card--main"
    >
      <StoreSetup
        :status="status.data.value"
        @retry="status.refetch()"
      />
    </div>

    <template v-else>
      <aside
        class="dashboards__card dashboards__rail"
        :style="{ flexBasis: `${String(shownRailWidth)}px` }"
        data-testid="dashboards-rail"
      >
        <DashboardsRailNarrow
          v-if="railNarrow"
          :own="listed.own"
          :shared="listed.shared"
          :current-id="current?.id ?? null"
          :may-set-up="status.data.value?.may_set_up === true"
          :creating="creating.isPending.value"
          @expand="railNarrow = false"
          @create="createDashboard"
          @select="(id) => (selectedId = id)"
          @sources="agentsOpen = true"
          @store="storeOpen = true"
        />
        <template v-else>
          <div class="dashboards__heading">
            <span>Dashboards</span>
            <span class="dashboards__actions">
              <AppButton
                variant="quiet"
                size="sm"
                icon="add"
                label="New"
                :loading="creating.isPending.value"
                data-testid="dashboard-new"
                @click="createDashboard"
              />
              <AppIconButton
                icon="chevron_left"
                tooltip="Hide"
                data-testid="dashboards-collapse"
                @click="railNarrow = true"
              />
            </span>
          </div>
          <div class="dashboards__list">
            <AppButton
              v-for="dashboard in listed.own"
              :key="dashboard.id"
              :variant="railEntry(dashboard.color, dashboard.id === current?.id).variant"
              :class="{
                'dashboards__entry--tinted': railEntry(dashboard.color, dashboard.id === current?.id).tinted,
                'dashboards__entry--filled': railEntry(dashboard.color, dashboard.id === current?.id).filled,
              }"
              :style="panelColorStyle(dashboard.color)"
              layout="navigation"
              size="sm"
              icon="dashboard"
              :label="dashboard.name"
              :data-testid="`dashboard-${dashboard.name}`"
              @click="selectedId = dashboard.id"
            />
          </div>

          <template v-if="listed.shared.length > 0">
            <div class="dashboards__heading dashboards__heading--divided">
              <span>Shared with you</span>
            </div>
            <div
              class="dashboards__list"
              data-testid="dashboards-shared"
            >
              <AppButton
                v-for="dashboard in listed.shared"
                :key="dashboard.id"
                :variant="railEntry(dashboard.color, dashboard.id === current?.id).variant"
                :class="{
                  'dashboards__entry--tinted': railEntry(dashboard.color, dashboard.id === current?.id).tinted,
                  'dashboards__entry--filled': railEntry(dashboard.color, dashboard.id === current?.id).filled,
                }"
                :style="panelColorStyle(dashboard.color)"
                layout="navigation"
                size="sm"
                icon="group"
                :label="dashboard.name"
                :data-testid="`dashboard-${dashboard.name}`"
                @click="selectedId = dashboard.id"
              >
                <AppTooltip>Shared by {{ dashboard.owner ?? "somebody" }}</AppTooltip>
              </AppButton>
            </div>
          </template>

          <div class="dashboards__heading dashboards__heading--divided">
            <span>Sources</span>
            <span>
              <AppIconButton
                v-if="status.data.value?.may_set_up"
                icon="storage"
                tooltip="The metrics store"
                data-testid="store-open"
                @click="storeOpen = true"
              />
              <AppButton
                variant="quiet"
                size="sm"
                icon="sensors"
                label="Sources"
                data-testid="agents-open"
                @click="agentsOpen = true"
              />
            </span>
          </div>
          <div class="dashboards__sources">
            <AppEmptyState
              v-if="sources.length === 0"
              text="Nothing reports yet"
            />
            <AppTree
              v-else
              v-model:expanded="sourcesExpanded"
              :nodes="sources"
              :selected="null"
              node-key="key"
            >
              <template #default-header="{ node }">
                <span>{{ node.label }}</span>
              </template>
            </AppTree>
          </div>
        </template>
      </aside>

      <WorkspaceSeparator
        direction="row"
        @move="resizeRail"
        @toggle="pressGap"
      />

      <section class="dashboards__card dashboards__card--main">
        <DashboardView
          v-if="current"
          :key="current.id"
          :dashboard="current"
          :catalog="catalog.data.value"
          :index="index"
          @agents="agentsOpen = true"
          @deleted="afterDelete"
        />
        <div
          v-else-if="dashboards.isPending.value"
          class="dashboards__center"
        >
          <AppSpinner />
        </div>
        <div
          v-else
          class="dashboards__center dashboards__center--stacked"
        >
          <span>No dashboards yet.</span>
          <AppButton
            icon="add"
            label="Create a dashboard"
            data-testid="dashboard-create-first"
            @click="createDashboard"
          />
        </div>
      </section>
    </template>

    <AgentsDialog v-model="agentsOpen" />
    <StoreDialog
      v-if="status.data.value?.may_set_up"
      v-model="storeOpen"
    />
  </div>
</template>

<style scoped>
/* No gap of its own: the separator between the two cards is that gap, and
   the handle that resizes them, as it is between workspace columns (D12). */
.dashboards {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
}

/* The same card a workspace section is (D12). */
.dashboards__card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  box-sizing: border-box;
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  background: var(--dp-surface);
}

.dashboards__rail {
  flex-grow: 0;
  flex-shrink: 0;
}

.dashboards__card--main {
  flex: 1;
}

.dashboards__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: var(--dp-tab-strip-height);
  padding: 0 var(--dp-space-1) 0 var(--dp-space-2);
  color: var(--dp-text-muted);
}

.dashboards__actions {
  display: flex;
  align-items: center;
}

/* A dashboard's own colour, as a connection's row carries it (railEntry.ts). */
.dashboards__entry--tinted {
  background: var(--dp-panel-quiet);
}

.dashboards__entry--filled {
  background: var(--dp-panel-background);
  color: var(--dp-panel-foreground);
}

.dashboards__heading--divided {
  border-top: 1px solid var(--dp-border-faint);
}

.dashboards__list {
  display: flex;
  flex-direction: column;
  padding: 0 var(--dp-space-1) var(--dp-space-2);
  max-height: 40%;
  overflow-y: auto;
}

.dashboards__sources {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 var(--dp-space-2) var(--dp-space-2);
}

.dashboards__center {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--dp-text-muted);
}

.dashboards__center--stacked {
  flex-direction: column;
  gap: var(--dp-space-3);
}
</style>
