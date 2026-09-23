<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"
import { computed, defineComponent, h, onBeforeUnmount, onMounted, ref, watch } from "vue"

import type { DashboardPublic, MetricsCatalog } from "@/client"
import { messageOf } from "@/shared/api/errors"
import {
  AppButton,
  AppCardHead,
  AppColorPicker,
  AppForm,
  AppIconButton,
  AppInput,
  AppSelect,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { panelColorStyle } from "@/shared/ui/panelColor"
import { openAsTabAction, useWindowManager, WindowDialog } from "@/shared/windows"
import { useWorkspaceActions } from "@/features/workspace/state"

import AddWidgetsDialog from "./AddWidgetsDialog.vue"
import { dashboardsKey, useDashboardCatalog, useDeleteDashboard, useSaveDashboard } from "./api"
import { indexCatalog } from "./catalog"
import type { SeriesEntry } from "./catalog"
import DashboardGrid from "./DashboardGrid.vue"
import DashboardShareDialog from "./DashboardShareDialog.vue"
import {
  MAX_WIDGETS,
  placedOf,
  RANGES,
  REFRESHES,
  renamed,
  withDrafts,
  withLayout,
  withOptions,
  withoutWidget,
  withPreset,
} from "./dashboardModel"
import type { ProcessLimit, ProcessSort, RangeSeconds, RefreshSeconds, Widget } from "./dashboardModel"
import type { Placed } from "./gridLayout"
import { mayEdit, mayManage, mergedIndex } from "./sharing"
import WidgetBody from "./WidgetBody.vue"
import WidgetFrame from "./WidgetFrame.vue"
import WidgetWindow from "./WidgetWindow.vue"
import type { WidgetDraft } from "./widgetSpecs"

/**
 * One dashboard. What is on it is held here as a draft and saved whole, a
 * moment after the last change, with the version it was read at: a save from
 * a second tab in between is refused rather than silently undone (D129).
 *
 * On a dashboard somebody may only view, nothing is saved: the range and the
 * interval they choose are theirs for as long as it is open.
 */
const props = defineProps<{
  dashboard: DashboardPublic
  catalog: MetricsCatalog | undefined
  index: Map<number, SeriesEntry>
}>()

const emit = defineEmits<{ agents: []; deleted: [] }>()

const SAVE_DELAY_MS = 800

const toast = useToast()
const confirm = useConfirm()
const queryClient = useQueryClient()
const saving = useSaveDashboard()
const deleting = useDeleteDashboard()
const windows = useWindowManager()
const workspace = useWorkspaceActions()

const name = ref(props.dashboard.name)
const color = ref<string | null>(props.dashboard.color ?? null)
const version = ref(props.dashboard.version)
const widgets = ref<Widget[]>([...(props.dashboard.widgets ?? [])])
const range = ref<RangeSeconds>(props.dashboard.options?.range_seconds ?? 900)
const refresh = ref<RefreshSeconds>(props.dashboard.options?.refresh_seconds ?? 30)
const expandedId = ref<string | null>(null)
const addOpen = ref(false)
const renameOpen = ref(false)
const renameDraft = ref("")
const shareOpen = ref(false)

const editable = computed(() => mayEdit(props.dashboard))
const manageable = computed(() => mayManage(props.dashboard))
const throughDashboard = useDashboardCatalog(() => props.dashboard.id)
const shownIndex = computed(() => mergedIndex(props.index, indexCatalog(throughDashboard.data.value)))

let timer: ReturnType<typeof setTimeout> | undefined
let pending = false

function schedule() {
  if (!editable.value) return
  pending = true
  clearTimeout(timer)
  timer = setTimeout(() => void save(), SAVE_DELAY_MS)
}

async function save() {
  if (!pending) return
  pending = false
  try {
    const saved = await saving.mutateAsync({
      id: props.dashboard.id,
      body: {
        name: name.value,
        color: color.value,
        version: version.value,
        options: { range_seconds: range.value, refresh_seconds: refresh.value },
        widgets: widgets.value,
      },
    })
    version.value = saved.version
  } catch (cause) {
    if (cause instanceof AxiosError && cause.response?.status === 409) {
      toast.error("This dashboard was changed somewhere else; it has been read again")
      await queryClient.invalidateQueries({ queryKey: dashboardsKey })
      return
    }
    toast.error(messageOf(cause, "The dashboard could not be saved"))
  }
}

// A dashboard read again from the server, after a conflict, replaces the draft.
watch(
  () => props.dashboard.version,
  (next) => {
    if (next === version.value || pending) return
    name.value = props.dashboard.name
    color.value = props.dashboard.color ?? null
    version.value = next
    widgets.value = [...(props.dashboard.widgets ?? [])]
    range.value = props.dashboard.options?.range_seconds ?? 900
    refresh.value = props.dashboard.options?.refresh_seconds ?? 30
  }
)

const placed = computed(() => placedOf(widgets.value))
const byId = computed(() => new Map(widgets.value.map((widget) => [widget.id, widget])))

function applyLayout(items: Placed[]) {
  widgets.value = withLayout(widgets.value, items)
  schedule()
}

function addDrafts(drafts: WidgetDraft[]) {
  const result = withDrafts(widgets.value, drafts, () => crypto.randomUUID())
  widgets.value = result.widgets
  if (result.left > 0) {
    toast.info(`${String(result.left)} of ${String(drafts.length)} did not fit: a dashboard holds ${String(MAX_WIDGETS)} widgets`)
  }
  schedule()
}

function addPreset(preset: Widget[]) {
  const result = withPreset(widgets.value, preset, () => crypto.randomUUID())
  widgets.value = result.widgets
  if (result.left > 0) {
    toast.info(`${String(result.left)} of ${String(preset.length)} did not fit: a dashboard holds ${String(MAX_WIDGETS)} widgets`)
  }
  schedule()
}

function setOptions(id: string, patch: { sort?: ProcessSort; limit?: ProcessLimit }) {
  widgets.value = withOptions(widgets.value, id, patch)
  schedule()
}

/**
 * The widget in a floating window, which belongs to both spaces (D125). A
 * window is identified by what it shows, so opening it twice brings it forward.
 */
function detach(widget: Widget) {
  const snapshot = {
    widget: { ...widget },
    rangeSeconds: range.value,
    refreshSeconds: refresh.value,
    dashboardId: props.dashboard.id,
  }
  const windowId = `metrics-widget:${props.dashboard.id}:${widget.id}`
  windows.open({
    id: windowId,
    look: { title: widget.title, icon: "dashboard" },
    size: widget.type === "stat" ? { width: 360, height: 240 } : { width: 760, height: 440 },
    // A chart takes the room it is given; fitting the frame to it would leave
    // a frame with no height.
    autoFit: false,
    // The window's contents can live as a workspace tab: opening the tab and
    // closing the window is one move, not a copy (D155).
    actions: [
      openAsTabAction(() => {
        workspace.openWidgetTab(snapshot)
        windows.close(windowId)
      }),
    ],
    component: defineComponent({
      name: "MetricsWidgetWindow",
      setup: () => () => h(WidgetWindow, snapshot),
    }),
  })
}

function removeWidget(id: string) {
  if (expandedId.value === id) expandedId.value = null
  widgets.value = withoutWidget(widgets.value, id)
  schedule()
}

function renameWidget(id: string, title: string) {
  widgets.value = renamed(widgets.value, id, title)
  schedule()
}

function chooseRange(value: unknown) {
  range.value = value as RangeSeconds
  schedule()
}

function chooseRefresh(value: unknown) {
  refresh.value = value as RefreshSeconds
  schedule()
}

function chooseColor(value: string | null) {
  color.value = value
  schedule()
}

function startRename() {
  renameDraft.value = name.value
  renameOpen.value = true
}

function applyRename() {
  const next = renameDraft.value.trim()
  if (next === "") return
  name.value = next.slice(0, 120)
  renameOpen.value = false
  schedule()
}

async function removeDashboard() {
  const sure = await confirm({
    title: "Delete this dashboard?",
    message: `${name.value} and its ${String(widgets.value.length)} widgets will be removed. The metrics stay.`,
    confirmLabel: "Delete",
    danger: true,
  })
  if (!sure) return
  pending = false
  clearTimeout(timer)
  try {
    await deleting.mutateAsync(props.dashboard.id)
    emit("deleted")
  } catch (cause) {
    toast.error(messageOf(cause, "The dashboard could not be deleted"))
  }
}

function onKey(event: KeyboardEvent) {
  if (event.key === "Escape" && expandedId.value !== null) expandedId.value = null
}

onMounted(() => window.addEventListener("keydown", onKey))
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey)
  clearTimeout(timer)
  void save()
})
</script>

<template>
  <div
    class="dashboard-view"
    data-testid="dashboard-view"
  >
    <AppCardHead data-testid="dashboard-head">
      <span
        class="dashboard-view__name"
        :class="{ 'dashboard-view__name--colored': color !== null }"
        :style="panelColorStyle(color)"
        data-testid="dashboard-name"
      >{{ name }}</span>
      <span
        v-if="!manageable"
        class="dashboard-view__shared"
        data-testid="dashboard-shared-by"
      >{{ editable ? "You can edit" : "View only" }} · shared by {{ dashboard.owner ?? "somebody" }}</span>
      <AppIconButton
        v-if="editable"
        icon="edit"
        tooltip="Rename this dashboard"
        @click="startRename"
      />
      <AppColorPicker
        v-if="editable"
        :model-value="color"
        label="Dashboard color"
        data-testid="dashboard-color"
        @update:model-value="chooseColor"
      />
      <AppIconButton
        icon="share"
        tooltip="Share this dashboard"
        data-testid="dashboard-share"
        @click="shareOpen = true"
      />
      <AppIconButton
        v-if="manageable"
        icon="delete"
        tooltip="Delete this dashboard"
        variant="danger-quiet"
        @click="removeDashboard"
      />
      <span class="dashboard-view__spacer" />
      <AppSelect
        :model-value="range"
        :options="RANGES"
        compact
        aria-label="Range"
        data-testid="dashboard-range"
        @update:model-value="chooseRange"
      />
      <AppSelect
        :model-value="refresh"
        :options="REFRESHES"
        compact
        aria-label="Refresh every"
        data-testid="dashboard-refresh"
        @update:model-value="chooseRefresh"
      />
      <AppButton
        v-if="editable"
        variant="secondary"
        size="sm"
        icon="add_chart"
        label="Add widgets"
        :disable="widgets.length >= MAX_WIDGETS"
        data-testid="dashboard-add"
        @click="addOpen = true"
      />
    </AppCardHead>

    <div class="dashboard-view__body">
      <div
        v-if="widgets.length === 0"
        class="dashboard-view__empty"
      >
        <span>Nothing on this dashboard yet.</span>
        <AppButton
          v-if="editable"
          icon="add_chart"
          label="Add widgets"
          @click="addOpen = true"
        />
      </div>
      <DashboardGrid
        v-else
        :items="placed"
        :expanded-id="expandedId"
        @layout="applyLayout"
      >
        <template #default="{ id, grab, grabResize }">
          <WidgetFrame
            v-if="byId.get(id)"
            :title="byId.get(id)?.title ?? ''"
            :expanded="expandedId === id"
            :editable="editable"
            @grab="grab"
            @grab-resize="grabResize"
            @rename="(title) => renameWidget(id, title)"
            @remove="removeWidget(id)"
            @toggle-expand="expandedId = expandedId === id ? null : id"
            @detach="detach(byId.get(id) as Widget)"
          >
            <WidgetBody
              :widget="byId.get(id) as Widget"
              :index="shownIndex"
              :range-seconds="range"
              :refresh-seconds="refresh"
              :dashboard-id="dashboard.id"
              @options="(patch) => setOptions(id, patch)"
            />
          </WidgetFrame>
        </template>
      </DashboardGrid>
    </div>

    <DashboardShareDialog
      v-model="shareOpen"
      :dashboard="dashboard"
    />

    <AddWidgetsDialog
      v-model="addOpen"
      :catalog="catalog"
      :index="index"
      :room="MAX_WIDGETS - widgets.length"
      @add="addDrafts"
      @add-preset="addPreset"
      @agents="emit('agents')"
    />

    <WindowDialog
      v-model="renameOpen"
      title="Rename dashboard"
      size="sm"
      sizing="content"
    >
      <AppForm layout="section">
        <AppInput
          v-model="renameDraft"
          label="Name"
          data-testid="dashboard-rename-input"
          @keydown.enter="applyRename"
        />
      </AppForm>
      <template #actions>
        <AppButton
          variant="quiet"
          label="Cancel"
          @click="renameOpen = false"
        />
        <AppButton
          label="Rename"
          :disable="renameDraft.trim() === ''"
          @click="applyRename"
        />
      </template>
    </WindowDialog>
  </div>
</template>

<style scoped>
.dashboard-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.dashboard-view__name {
  color: var(--dp-text-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Filled as a connection's tab is with its colour, and written in the colour
   that stays readable on it. */
.dashboard-view__name--colored {
  padding: 0 var(--dp-space-2);
  border-radius: var(--dp-radius-control);
  background: var(--dp-panel-background);
  color: var(--dp-panel-foreground);
}

.dashboard-view__shared {
  color: var(--dp-text-muted);
  white-space: nowrap;
}

.dashboard-view__spacer {
  flex: 1;
}

.dashboard-view__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--dp-space-2);
}

.dashboard-view__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--dp-space-3);
  height: 100%;
  color: var(--dp-text-muted);
}
</style>
