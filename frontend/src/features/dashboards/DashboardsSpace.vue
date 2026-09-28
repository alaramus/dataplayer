<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, nextTick, ref, watch } from "vue"

import { messageOf } from "@/shared/api/errors"
import { serverStorageKey } from "@/shared/servers/context"
import {
  AppButton,
  AppCardFrame,
  AppCardHead,
  AppEmptyState,
  AppIconButton,
  AppInput,
  AppSpinner,
  AppTooltip,
  AppTree,
  useToast,
} from "@/shared/ui"
import { panelColorStyle } from "@/shared/ui/panelColor"
import { WorkspaceSeparator } from "@/shared/workspace"
import { useSideRail } from "@/shared/workspace/useSideRail"

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
import { railRules } from "./railRules"
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

// The sources fold at the foot of the rail and open to half of it, so the
// dashboards take the whole height until somebody asks for the sources.
const SOURCES_OPEN_KEY = serverStorageKey("dataplayer-dashboard-sources-open")
function storedSourcesOpen(): boolean {
  try {
    return localStorage.getItem(SOURCES_OPEN_KEY) === "true"
  } catch {
    return false
  }
}
const sourcesOpen = ref(storedSourcesOpen())
function toggleSources() {
  sourcesOpen.value = !sourcesOpen.value
  try {
    localStorage.setItem(SOURCES_OPEN_KEY, String(sourcesOpen.value))
  } catch {
    // Remembering it is a courtesy.
  }
}
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
const dashboardNameFilter = ref("")
const dashboardFilterOpen = ref(false)
const dashboardFilterField = ref<InstanceType<typeof AppInput> | null>(null)
const shownDashboards = computed(() => {
  const query = dashboardNameFilter.value.trim().toLocaleLowerCase()
  const matches = (name: string) => !query || name.toLocaleLowerCase().includes(query)
  return {
    own: listed.value.own.filter((dashboard) => matches(dashboard.name)),
    shared: listed.value.shared.filter((dashboard) => matches(dashboard.name)),
  }
})
const rules = computed(() => railRules(shownDashboards.value.own.length, shownDashboards.value.shared.length))

async function openDashboardFilter() {
  dashboardFilterOpen.value = true
  await nextTick()
  ;(dashboardFilterField.value?.$el as HTMLElement | undefined)?.querySelector("input")?.focus()
}
function closeDashboardFilter() {
  dashboardNameFilter.value = ""
  dashboardFilterOpen.value = false
}

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
  const listed = dashboards.data.value ?? []
  const count = listed.length
  try {
    const created = await creating.mutateAsync(count === 0 ? "My dashboard" : `Dashboard ${String(count + 1)}`)
    selectedId.value = created.id
    // The server gives back an empty dashboard the person already has rather
    // than making a second (D129).
    if (listed.some((one) => one.id === created.id)) {
      toast.info(`"${created.name}" is still empty. Add something to it before starting another dashboard.`)
    }
  } catch (cause) {
    toast.error(messageOf(cause, "The dashboard could not be created"))
  }
}

function afterDelete() {
  selectedId.value = null
}

const spaceElement = ref<HTMLElement | null>(null)
const {
  narrow: railNarrow,
  shownWidth: shownRailWidth,
  resize: resizeRail,
  pressGap,
} = useSideRail(spaceElement, {
  width: serverStorageKey("dataplayer-dashboards-rail"),
  narrow: serverStorageKey("dataplayer-dashboards-rail-narrow"),
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
    <!-- Every card has its head, whatever state it is in: a card without one
         is what made this space look like a different application. -->
    <AppCardFrame
      v-if="status.isPending.value"
      tag="section"
      class="dashboards__main"
    >
      <AppCardHead title="Dashboards" />
      <div class="dashboards__center">
        <AppSpinner />
      </div>
    </AppCardFrame>

    <AppCardFrame
      v-else-if="status.isError.value"
      tag="section"
      class="dashboards__main"
    >
      <AppCardHead title="Dashboards" />
      <div class="dashboards__center">
        <AppEmptyState
          icon="error"
          :text="messageOf(status.error.value, 'Dashboards could not be read')"
        />
      </div>
    </AppCardFrame>

    <AppCardFrame
      v-else-if="status.data.value && !ready"
      tag="section"
      class="dashboards__main"
    >
      <AppCardHead title="Dashboards" />
      <div class="dashboards__scroll">
        <StoreSetup
          :status="status.data.value"
          @retry="status.refetch()"
        />
      </div>
    </AppCardFrame>

    <template v-else>
      <AppCardFrame
        tag="aside"
        class="dashboards__rail"
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
          @create="createDashboard"
          @select="(id) => (selectedId = id)"
          @sources="agentsOpen = true"
          @store="storeOpen = true"
        />
        <template v-else>
          <AppCardHead
            v-if="dashboardFilterOpen"
            class="dashboards__filter-head"
            @keydown.esc.stop="closeDashboardFilter"
          >
            <AppInput
              ref="dashboardFilterField"
              v-model="dashboardNameFilter"
              compact
              placeholder="Filter dashboards"
              aria-label="Filter dashboards by name"
              autocomplete="off"
              data-testid="dashboards-name-filter"
            />
            <template #actions>
              <AppIconButton
                :icon="appIcons.close"
                tooltip="Close dashboard filter"
                data-testid="dashboards-filter-close"
                @click="closeDashboardFilter"
              />
            </template>
          </AppCardHead>
          <AppCardHead
            v-else
            title="Dashboards"
          >
            <template #actions>
              <!-- The header button collapses this rail; no chevron of its own. -->
              <AppIconButton
                :icon="appIcons.add"
                tooltip="New dashboard"
                :loading="creating.isPending.value"
                data-testid="dashboard-new"
                @click="createDashboard"
              />
              <AppIconButton
                :icon="appIcons.search"
                tooltip="Filter dashboards by name"
                data-testid="dashboards-filter-open"
                @click="openDashboardFilter"
              />
              <AppIconButton
                :icon="appIcons.sensors"
                tooltip="Sources"
                data-testid="agents-open"
                @click="agentsOpen = true"
              />
              <AppIconButton
                v-if="status.data.value?.may_set_up"
                :icon="appIcons.storage"
                tooltip="The metrics store"
                data-testid="store-open"
                @click="storeOpen = true"
              />
            </template>
          </AppCardHead>
          <!-- Down to the sources at the foot, and scrolled there. -->
          <div
            class="dashboards__lists"
            data-testid="dashboards-lists"
          >
            <!-- Absent rather than empty, or its padding stood as a gap under the
               head. A line stands only between groups that both show
               something (railRules). -->
            <div
              v-if="shownDashboards.own.length > 0"
              class="dashboards__list"
            >
              <AppButton
                v-for="dashboard in shownDashboards.own"
                :key="dashboard.id"
                :variant="railEntry(dashboard.color, dashboard.id === current?.id).variant"
                :class="{
                  'dashboards__entry--tinted': railEntry(dashboard.color, dashboard.id === current?.id).tinted,
                  'dashboards__entry--filled': railEntry(dashboard.color, dashboard.id === current?.id).filled,
                }"
                :style="panelColorStyle(dashboard.color)"
                layout="navigation"
                size="sm"
                :icon="appIcons.dashboard"
                :label="dashboard.name"
                :data-testid="`dashboard-${dashboard.name}`"
                @click="selectedId = dashboard.id"
              />
            </div>

            <template v-if="shownDashboards.shared.length > 0">
              <div
                class="dashboards__heading"
                :class="{ 'dashboards__heading--divided': rules.beforeShared }"
              >
                <span>Shared with you</span>
              </div>
              <div
                class="dashboards__list"
                data-testid="dashboards-shared"
              >
                <AppButton
                  v-for="dashboard in shownDashboards.shared"
                  :key="dashboard.id"
                  :variant="railEntry(dashboard.color, dashboard.id === current?.id).variant"
                  :class="{
                    'dashboards__entry--tinted': railEntry(dashboard.color, dashboard.id === current?.id).tinted,
                    'dashboards__entry--filled': railEntry(dashboard.color, dashboard.id === current?.id).filled,
                  }"
                  :style="panelColorStyle(dashboard.color)"
                  layout="navigation"
                  size="sm"
                  :icon="appIcons.group"
                  :label="dashboard.name"
                  :data-testid="`dashboard-${dashboard.name}`"
                  @click="selectedId = dashboard.id"
                >
                  <AppTooltip>{{ dashboard.name }}, shared by {{ dashboard.owner ?? "somebody" }}</AppTooltip>
                </AppButton>
              </div>
            </template>

            <AppEmptyState
              v-if="dashboardNameFilter.trim() && shownDashboards.own.length === 0 && shownDashboards.shared.length === 0"
              text="No matching dashboards"
            />
          </div>

          <div
            class="dashboards__sources-fold"
            :class="{ 'dashboards__sources-fold--open': sourcesOpen }"
          >
            <button
              type="button"
              class="dashboards__heading dashboards__heading--divided dashboards__sources-toggle"
              :aria-expanded="sourcesOpen"
              data-testid="dashboards-sources-toggle"
              @click="toggleSources"
            >
              <span>Sources</span>
              <q-icon
                :name="sourcesOpen ? appIcons.keyboardArrowDown : appIcons.keyboardArrowUp"
                size="20px"
              />
            </button>
            <div
              v-if="sourcesOpen"
              class="dashboards__sources"
              data-testid="dashboards-sources"
            >
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
          </div>
        </template>
      </AppCardFrame>

      <WorkspaceSeparator
        direction="row"
        @move="resizeRail"
        @toggle="pressGap"
      />

      <AppCardFrame
        tag="section"
        class="dashboards__main"
      >
        <DashboardView
          v-if="current"
          :key="current.id"
          :dashboard="current"
          :catalog="catalog.data.value"
          :index="index"
          @agents="agentsOpen = true"
          @deleted="afterDelete"
        />
        <template v-else>
          <!-- Empty, as an empty column of Data keeps its strip. -->
          <AppCardHead />
          <div
            v-if="dashboards.isPending.value"
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
              :icon="appIcons.add"
              label="Create a dashboard"
              data-testid="dashboard-create-first"
              @click="createDashboard"
            />
          </div>
        </template>
      </AppCardFrame>
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

.dashboards__rail {
  flex-grow: 0;
  flex-shrink: 0;
}

.dashboards__main {
  flex: 1;
}

.dashboards__filter-head > :first-child { flex: 1; min-width: 0; }

.dashboards__scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

/* A group inside the rail, under the card's own head. */
.dashboards__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: var(--dp-tab-strip-height);
  padding: 0 var(--dp-space-1) 0 var(--dp-space-2);
  color: var(--dp-text-muted);
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

.dashboards__lists {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.dashboards__list {
  display: flex;
  flex-direction: column;
  padding: 0 var(--dp-space-1) var(--dp-space-2);
}

/* Folded, only its line at the foot; open, the lower half of the rail. */
.dashboards__sources-fold {
  flex: none;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.dashboards__sources-fold--open {
  flex: 0 0 50%;
}

.dashboards__sources-toggle {
  flex: none;
  width: 100%;
  border: none;
  background: none;
  font: inherit;
  cursor: pointer;
}

.dashboards__sources-toggle:hover {
  background: var(--dp-hover);
}

.dashboards__sources-toggle:focus-visible {
  outline: 2px solid var(--dp-focus-border);
  outline-offset: calc(-1 * var(--dp-space-half));
}

.dashboards__sources {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 var(--dp-space-2) var(--dp-space-2);
}

.dashboards__center {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--dp-text-muted);
}

.dashboards__center--stacked {
  flex-direction: column;
  gap: var(--dp-space-3);
}
</style>
