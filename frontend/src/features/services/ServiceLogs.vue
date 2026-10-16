<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, toRef, watch } from "vue"

import AutoRefreshButton from "@/features/grid/AutoRefreshButton.vue"
import { REFRESH_SECONDS } from "@/features/grid/autoRefresh"
import type { RefreshSeconds } from "@/features/grid/autoRefresh"
import { useServiceLogs } from "@/features/services/api"
import { t } from "@/shared/i18n"
import { serverStorageKey } from "@/shared/servers/context"
import { AppEmptyState, AppIconButton, AppSpinner } from "@/shared/ui"

/**
 * What a service printed: the container's own output and nothing else (D84).
 * A tail rather than a stream — the question is "why did it not start", and
 * that is answered by the last few hundred lines. Drawn in a window and, once
 * it is moved, in a workspace tab (D155).
 */
const props = defineProps<{
  serviceId: string | null
}>()

const logs = useServiceLogs(toRef(props, "serviceId"))
const refreshSeconds = ref<RefreshSeconds | null>(null)
const panelShown = ref(true)
const windowShown = ref(true)
const onScreen = computed(() => panelShown.value && windowShown.value && props.serviceId !== null)
const held = computed(() => !onScreen.value
  ? t("services.logs.held_away")
  : logs.isFetching.value ? t("grid.refresh.held.fetching") : null)

function refreshKey(serviceId: string): string {
  return serverStorageKey(`dataplayer:service-logs:refresh:${serviceId}`)
}

function rememberedRefresh(serviceId: string | null): RefreshSeconds | null {
  if (serviceId === null) return null
  try {
    const stored = localStorage.getItem(refreshKey(serviceId))
    if (stored === null) return 5
    const value: unknown = JSON.parse(stored)
    return REFRESH_SECONDS.find((seconds) => seconds === value) ?? null
  } catch {
    return 5
  }
}

async function refresh() {
  if (props.serviceId === null || logs.isFetching.value) return
  await logs.refetch()
}

let ticking: ReturnType<typeof setInterval> | undefined
function stopTicking() {
  if (ticking !== undefined) clearInterval(ticking)
  ticking = undefined
}
function startTicking() {
  stopTicking()
  const seconds = refreshSeconds.value
  if (seconds === null) return
  ticking = setInterval(() => {
    if (held.value === null) void refresh()
  }, seconds * 1000)
}
function chooseRefresh(seconds: RefreshSeconds | null) {
  refreshSeconds.value = seconds
  if (props.serviceId !== null) {
    try { localStorage.setItem(refreshKey(props.serviceId), JSON.stringify(seconds)) }
    catch { /* Refresh still works while browser storage is unavailable. */ }
  }
  if (seconds !== null && held.value === null) void refresh()
}
function noteWindow() { windowShown.value = document.visibilityState === "visible" }

watch(() => props.serviceId, (serviceId) => { refreshSeconds.value = rememberedRefresh(serviceId) }, { immediate: true })
watch(refreshSeconds, startTicking)
watch(onScreen, (shown) => {
  if (shown) void refresh()
})
onMounted(() => {
  noteWindow()
  document.addEventListener("visibilitychange", noteWindow)
  startTicking()
})
onActivated(() => { panelShown.value = true })
onDeactivated(() => { panelShown.value = false })
onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", noteWindow)
  stopTicking()
})
</script>

<template>
  <div class="service-logs">
    <div class="service-logs__controls">
      <AutoRefreshButton
        :seconds="refreshSeconds"
        :held="held"
        :disable="serviceId === null"
        test-id="service-logs-auto-refresh"
        @update:seconds="chooseRefresh"
      />
      <AppIconButton
        :icon="appIcons.refresh"
        :tooltip="t('services.logs.refresh')"
        :loading="logs.isFetching.value"
        :disable="serviceId === null"
        data-testid="service-logs-refresh"
        @click="refresh"
      />
    </div>
    <AppSpinner v-if="logs.isLoading.value" />
    <AppEmptyState
      v-else-if="(logs.data.value?.lines.length ?? 0) === 0"
      icon="notes"
      :text="t('services.logs.empty')"
    />
    <pre
      v-else
      class="service-logs__text"
    >{{ logs.data.value?.lines.join("\n") }}</pre>
  </div>
</template>

<style scoped>
.service-logs {
  height: 100%;
  min-height: 0;
  flex: 1;
  box-sizing: border-box;
  overflow: auto;
  background: var(--dp-surface-raised);
}
.service-logs__controls {
  position: sticky;
  top: 0;
  z-index: var(--dp-layer-sticky);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--dp-space-1);
  height: var(--dp-toolbar-height);
  padding-right: var(--dp-space-2);
  background: var(--dp-surface-raised);
}
.service-logs__text {
  margin: 0;
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-sm);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
