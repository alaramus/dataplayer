<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { messageOf } from "@/shared/api/errors"
import { serverStorageKey } from "@/shared/servers/context"
import { AppButton, AppEmptyState, AppSpinner, AppTree, useToast } from "@/shared/ui"

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
</script>

<template>
  <div
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
        data-testid="dashboards-rail"
      >
        <div class="dashboards__heading">
          <span>Dashboards</span>
          <AppButton
            variant="quiet"
            size="sm"
            icon="add"
            label="New"
            :loading="creating.isPending.value"
            data-testid="dashboard-new"
            @click="createDashboard"
          />
        </div>
        <div class="dashboards__list">
          <AppButton
            v-for="dashboard in dashboards.data.value ?? []"
            :key="dashboard.id"
            :variant="dashboard.id === current?.id ? 'secondary' : 'quiet'"
            layout="navigation"
            size="sm"
            icon="dashboard"
            :label="dashboard.name"
            :data-testid="`dashboard-${dashboard.name}`"
            @click="selectedId = dashboard.id"
          />
        </div>

        <div class="dashboards__heading dashboards__heading--divided">
          <span>Sources</span>
          <AppButton
            variant="quiet"
            size="sm"
            icon="sensors"
            label="Sources"
            data-testid="agents-open"
            @click="agentsOpen = true"
          />
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
      </aside>

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
  </div>
</template>

<style scoped>
.dashboards {
  display: flex;
  gap: var(--dp-workspace-inset);
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
  box-shadow: 0 1px 4px var(--dp-shadow-soft);
}

.dashboards__rail {
  flex: 0 0 260px;
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
