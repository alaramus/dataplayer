<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, nextTick, onActivated, onDeactivated, provide, readonly, ref, watch } from "vue"

import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
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
import { dashboardsShownKey } from "./onScreen"
import DashboardView from "./DashboardView.vue"
import { dashboardIntent, takeDashboardIntent } from "./intent"
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
const shown = ref(true)
onActivated(() => { shown.value = true })
onDeactivated(() => { shown.value = false })
provide(dashboardsShownKey, readonly(shown))
useLivePoints(shown)

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

const selectedId = ref<string | null>(storedSelection())
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

/**
 * Said once the list is there: the same words for a dashboard that is gone and
 * one nobody shared, as the server gives (D33).
 */
function sayIfMissing(asked: string) {
  const said = (list: readonly { id: string }[] | undefined) => {
    if (list === undefined) return false
    if (!list.some((one) => one.id === asked)) {
      toast.error(t("dashboards.space.missing"))
    }
    return true
  }
  if (said(dashboards.data.value)) return
  const stop = watch(() => dashboards.data.value, (list) => {
    if (said(list)) stop()
  })
}

// A link followed here, or a dashboard found by the search, opens over the one
// last open.
watch(
  dashboardIntent,
  (asked) => {
    if (asked === null) return
    takeDashboardIntent()
    selectedId.value = asked
    sayIfMissing(asked)
  },
  { immediate: true }
)

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
    const created = await creating.mutateAsync(
      count === 0 ? t("dashboards.space.first_name") : t("dashboards.space.nth_name", { n: count + 1 })
    )
    selectedId.value = created.id
    // The server gives back an empty dashboard the person already has rather
    // than making a second (D129).
    if (listed.some((one) => one.id === created.id)) {
      toast.info(t("dashboards.space.still_empty", { name: created.name }))
    }
  } catch (cause) {
    toast.error(messageOf(cause, t("dashboards.space.create_failed")))
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
      <AppCardHead :title="t('dashboards.space.title')" />
      <div class="dashboards__center">
        <AppSpinner />
      </div>
    </AppCardFrame>

    <AppCardFrame
      v-else-if="status.isError.value"
      tag="section"
      class="dashboards__main"
    >
      <AppCardHead :title="t('dashboards.space.title')" />
      <div class="dashboards__center">
        <AppEmptyState
          icon="error"
          :text="messageOf(status.error.value, t('dashboards.space.read_failed'))"
        />
      </div>
    </AppCardFrame>

    <AppCardFrame
      v-else-if="status.data.value && !ready"
      tag="section"
      class="dashboards__main"
    >
      <AppCardHead :title="t('dashboards.space.title')" />
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
              :placeholder="t('dashboards.space.filter')"
              :aria-label="t('dashboards.space.filter_by_name')"
              autocomplete="off"
              data-testid="dashboards-name-filter"
            />
            <template #actions>
              <AppIconButton
                :icon="appIcons.close"
                :tooltip="t('dashboards.space.close_filter')"
                data-testid="dashboards-filter-close"
                @click="closeDashboardFilter"
              />
            </template>
          </AppCardHead>
          <AppCardHead
            v-else
            :title="t('dashboards.space.title')"
          >
            <template #actions>
              <!-- The header button collapses this rail; no chevron of its own. -->
              <AppIconButton
                :icon="appIcons.add"
                :tooltip="t('dashboards.space.new_dashboard')"
                :loading="creating.isPending.value"
                data-testid="dashboard-new"
                @click="createDashboard"
              />
              <AppIconButton
                :icon="appIcons.search"
                :tooltip="t('dashboards.space.filter_by_name')"
                data-testid="dashboards-filter-open"
                @click="openDashboardFilter"
              />
              <AppIconButton
                :icon="appIcons.sensors"
                :tooltip="t('dashboards.common.sources')"
                data-testid="agents-open"
                @click="agentsOpen = true"
              />
              <AppIconButton
                v-if="status.data.value?.may_set_up"
                :icon="appIcons.storage"
                :tooltip="t('dashboards.space.store')"
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
            <!-- Names alone: the icons are the narrow rail's, where there is no
               room for a name.
               Absent rather than empty, or its padding stood as a gap under the
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
                class="dashboards__entry"
                :class="{
                  'dashboards__entry--current': railEntry(dashboard.color, dashboard.id === current?.id).current,
                  'dashboards__entry--tinted': railEntry(dashboard.color, dashboard.id === current?.id).tinted,
                  'dashboards__entry--filled': railEntry(dashboard.color, dashboard.id === current?.id).filled,
                }"
                :style="panelColorStyle(dashboard.color)"
                layout="navigation"
                size="sm"
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
                <span>{{ t('dashboards.space.shared_with_you') }}</span>
              </div>
              <div
                class="dashboards__list"
                data-testid="dashboards-shared"
              >
                <AppButton
                  v-for="dashboard in shownDashboards.shared"
                  :key="dashboard.id"
                  :variant="railEntry(dashboard.color, dashboard.id === current?.id).variant"
                  class="dashboards__entry"
                  :class="{
                    'dashboards__entry--current': railEntry(dashboard.color, dashboard.id === current?.id).current,
                    'dashboards__entry--tinted': railEntry(dashboard.color, dashboard.id === current?.id).tinted,
                    'dashboards__entry--filled': railEntry(dashboard.color, dashboard.id === current?.id).filled,
                  }"
                  :style="panelColorStyle(dashboard.color)"
                  layout="navigation"
                  size="sm"
                  :label="dashboard.name"
                  :data-testid="`dashboard-${dashboard.name}`"
                  @click="selectedId = dashboard.id"
                >
                  <AppTooltip>
                    {{ t('dashboards.common.shared_by', { name: dashboard.name, owner: dashboard.owner ?? t('dashboards.common.somebody') }) }}
                  </AppTooltip>
                </AppButton>
              </div>
            </template>

            <AppEmptyState
              v-if="!dashboards.isPending.value && shownDashboards.own.length === 0 && shownDashboards.shared.length === 0"
              class="dashboards__empty"
              :text="dashboardNameFilter.trim() ? t('dashboards.space.no_matching') : t('dashboards.space.none_yet')"
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
              <span>{{ t('dashboards.common.sources') }}</span>
              <q-icon
                :name="sourcesOpen ? appIcons.keyboardArrowDown : appIcons.keyboardArrowUp"
                size="var(--dp-icon-md)"
              />
            </button>
            <div
              v-if="sourcesOpen"
              class="dashboards__sources"
              data-testid="dashboards-sources"
            >
              <AppEmptyState
                v-if="sources.length === 0"
                :text="t('dashboards.space.nothing_reports')"
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
          :busy="creating.isPending.value"
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
            <span>{{ t('dashboards.space.none_yet_sentence') }}</span>
            <AppButton
              :icon="appIcons.add"
              :label="t('dashboards.space.create')"
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

/* The open one, when it has no colour of its own (railEntry.ts). */
.dashboards__entry--current {
  background: var(--dp-tab-current);
  font-weight: 500;
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
  padding: 0 0 var(--dp-space-2);
}

/* Like a connection's row (ConnectorList): edge to edge and square, one row
   tall — not a rounded entry inset by the list's padding. */
.dashboards__list .dashboards__entry {
  width: 100%;
  min-height: var(--dp-row-height);
  border-radius: 0;
}

/* The eight pixels the Data list leaves round its empty line. */
.dashboards__empty {
  padding: var(--dp-space-2);
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
