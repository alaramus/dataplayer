<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { useQueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"
import { computed, defineComponent, h, onBeforeUnmount, onMounted, ref, watch } from "vue"

import type { DashboardPublic, MetricsCatalog } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
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
import { newId } from "@/shared/ids"

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
  /**
   * Another dashboard is being made and is about to replace this one. Its
   * commands wait: Rename pressed in that moment opened a window on this
   * dashboard, which went with it when the new one took its place.
   */
  busy?: boolean
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
      toast.error(t("dashboards.view.changed_elsewhere"))
      await queryClient.invalidateQueries({ queryKey: dashboardsKey })
      return
    }
    toast.error(messageOf(cause, t("dashboards.view.save_failed")))
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
  const result = withDrafts(widgets.value, drafts, () => newId())
  widgets.value = result.widgets
  if (result.left > 0) {
    toast.info(t("dashboards.view.did_not_fit", { left: result.left, total: drafts.length, max: MAX_WIDGETS }))
  }
  schedule()
}

function addPreset(preset: Widget[]) {
  const result = withPreset(widgets.value, preset, () => newId())
  widgets.value = result.widgets
  if (result.left > 0) {
    toast.info(t("dashboards.view.did_not_fit", { left: result.left, total: preset.length, max: MAX_WIDGETS }))
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
    look: { title: widget.title, icon: appIcons.dashboard },
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
    title: t("dashboards.view.delete_title"),
    message: t("dashboards.view.delete_message", { name: name.value, n: widgets.value.length }, widgets.value.length),
    confirmLabel: t("dashboards.view.delete_confirm"),
    danger: true,
  })
  if (!sure) return
  pending = false
  clearTimeout(timer)
  try {
    await deleting.mutateAsync(props.dashboard.id)
    emit("deleted")
  } catch (cause) {
    toast.error(messageOf(cause, t("dashboards.view.delete_failed")))
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
      >{{ t('dashboards.view.shared_by', {
        access: editable ? t('dashboards.view.you_can_edit') : t('dashboards.view.view_only'),
        owner: dashboard.owner ?? t('dashboards.common.somebody'),
      }) }}</span>
      <AppIconButton
        v-if="editable"
        :icon="appIcons.edit"
        :tooltip="t('dashboards.view.rename')"
        :disable="busy"
        @click="startRename"
      />
      <AppColorPicker
        v-if="editable"
        :model-value="color"
        :label="t('dashboards.view.color')"
        :disable="busy"
        data-testid="dashboard-color"
        @update:model-value="chooseColor"
      />
      <AppIconButton
        :icon="appIcons.share"
        :tooltip="t('dashboards.view.share')"
        :disable="busy"
        data-testid="dashboard-share"
        @click="shareOpen = true"
      />
      <AppIconButton
        v-if="manageable"
        :icon="appIcons.delete"
        :tooltip="t('dashboards.view.delete')"
        variant="danger-quiet"
        :disable="busy"
        @click="removeDashboard"
      />
      <span class="dashboard-view__spacer" />
      <AppSelect
        :model-value="range"
        :options="RANGES"
        compact
        :aria-label="t('dashboards.view.range')"
        data-testid="dashboard-range"
        @update:model-value="chooseRange"
      />
      <AppSelect
        :model-value="refresh"
        :options="REFRESHES"
        compact
        :aria-label="t('dashboards.view.refresh_every')"
        data-testid="dashboard-refresh"
        @update:model-value="chooseRefresh"
      />
      <AppButton
        v-if="editable"
        variant="secondary"
        size="sm"
        :icon="appIcons.addChart"
        :label="t('dashboards.view.add_widgets')"
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
        <span>{{ t('dashboards.view.empty') }}</span>
        <AppButton
          v-if="editable"
          :icon="appIcons.addChart"
          :label="t('dashboards.view.add_widgets')"
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
      :title="t('dashboards.view.rename_title')"
      size="sm"
      sizing="content"
    >
      <AppForm layout="section">
        <!-- Trap: closed on keydown, the window hands focus back to the
             pencil that opened it, and the same Enter presses that and
             opens it again. Prevented, the Enter ends here. -->
        <AppInput
          v-model="renameDraft"
          :label="t('dashboards.view.name')"
          data-testid="dashboard-rename-input"
          @keydown.enter.prevent="applyRename"
        />
      </AppForm>
      <template #actions>
        <AppButton
          variant="quiet"
          :label="t('dashboards.common.cancel')"
          @click="renameOpen = false"
        />
        <AppButton
          :label="t('dashboards.view.rename_confirm')"
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
