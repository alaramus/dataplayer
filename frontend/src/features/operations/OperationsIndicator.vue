<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, defineComponent, h, onBeforeUnmount, ref, watch } from "vue"

import { connectorsKey, useConnectors } from "@/features/connectors/api"
import { backupsKey, servicesKey, useCancelJob, useServices } from "@/features/services/api"
import { messageOf } from "@/shared/api/errors"
import { isActive, useOperations } from "@/shared/operations"
import { AppButton, AppProgress, AppTooltip, useToast } from "@/shared/ui"
import { useWindowManager } from "@/shared/windows"
import { useJobs } from "./api"
import ProcessesWindow from "./ProcessesWindow.vue"
import { foreground, localRow, serverRow } from "./presentation"
import type { ProcessRow } from "./presentation"

const jobs = useJobs()
const queryClient = useQueryClient()
const services = useServices()
const connectors = useConnectors()
const operations = useOperations()
const windows = useWindowManager()
const cancel = useCancelJob()
const toast = useToast()
const stopping = ref(new Set<string>())
const hidden = ref(new Set<string>())
const serverJobs = computed(() => [...new Map(
  (jobs.data.value?.pages.flatMap((page) => page.data) ?? []).map((job) => [job.id, job])
).values()])
// Polling may be how a missed terminal event is discovered. Re-read its
// subjects too, so a completed service becomes an available connection.
watch(() => serverJobs.value.map((job) => `${job.id}:${job.state}`).join(","), () => {
  void queryClient.invalidateQueries({ queryKey: servicesKey })
  void queryClient.invalidateQueries({ queryKey: backupsKey })
  void queryClient.invalidateQueries({ queryKey: connectorsKey })
  stopping.value = new Set([...stopping.value].filter((id) => {
    const job = serverJobs.value.find((item) => item.id === id)
    return job === undefined || job.state === "queued" || job.state === "running"
  }))
})
const rows = computed(() => {
  const server = serverJobs.value.map((job) => {
    const subject = job.kind.startsWith("service.")
      ? services.data.value?.find((service) => service.id === job.subject_id)?.connector_name
      : connectors.data.value?.find((connector) => connector.id === job.subject_id)?.name
    return serverRow(job, subject)
  }).filter((row) => row.active || !hidden.value.has(row.id))
  return [...operations.items.value.map(localRow), ...server]
    .sort((a, b) => Number(b.active) - Number(a.active) || b.createdAt - a.createdAt)
})
const activeCount = computed(() => operations.items.value.filter(isActive).length +
  (jobs.data.value?.pages[0]?.active_count ?? 0))
const current = computed(() => foreground(rows.value))
const caption = computed(() => {
  if (current.value) return current.value.label
  if (jobs.isError.value) return "Processes unavailable"
  return "Processes"
})
const error = computed(() => jobs.isError.value
  ? messageOf(jobs.error.value, "Server processes could not be refreshed. Last known state is shown.") : "")

async function stop(row: ProcessRow) {
  if (row.source === "local") { operations.stop(row.id); return }
  if (stopping.value.has(row.id)) return
  stopping.value = new Set([...stopping.value, row.id])
  try {
    await cancel.mutateAsync(row.id)
  } catch (cause) {
    toast.error(messageOf(cause, "The job could not be stopped"))
    const next = new Set(stopping.value)
    next.delete(row.id)
    stopping.value = next
  }
}

function clear() {
  operations.clearFinished()
  hidden.value = new Set([...hidden.value, ...rows.value.filter((row) => !row.active).map((row) => row.id)])
}

const content = defineComponent({
  setup: () => () => h(ProcessesWindow, {
    rows: rows.value, error: error.value, loading: jobs.isFetching.value,
    more: jobs.hasNextPage.value, stopping: stopping.value,
    onPause: (row: ProcessRow) => operations.pause(row.id),
    onResume: (row: ProcessRow) => operations.resume(row.id),
    onStop: stop, onClear: clear,
    onMore: () => { void jobs.fetchNextPage() },
    onRefresh: () => { void jobs.refetch() },
  }),
})

function open() {
  windows.open({
    id: "processes", look: { title: "Processes", icon: "pending_actions" },
    size: { width: 720, height: 420 }, minSize: { width: 320, height: 220 },
    component: content,
  })
}
onBeforeUnmount(() => { if (windows.isOpen("processes")) windows.close("processes") })
</script>

<template>
  <AppButton
    variant="quiet"
    size="sm"
    class="operations-indicator"
    aria-label="Show processes"
    data-testid="operations-indicator"
    @click="open"
  >
    <span class="operations-indicator__content">
      <span class="operations-indicator__caption">
        <q-icon :name="jobs.isError.value ? 'sync_problem' : current?.paused ? 'pause' : 'pending_actions'" />
        <span>{{ caption }}</span>
        <span v-if="activeCount > 1">+{{ activeCount - 1 }}</span>
      </span>
      <AppProgress
        v-if="current"
        :label="current.label"
        :value="current.progress"
        :paused="current.paused"
      />
    </span>
    <AppTooltip>{{ current ? `${current.status}: ${current.detail}. ` : '' }}Show processes</AppTooltip>
  </AppButton>
</template>

<style scoped>
.operations-indicator { min-width: 110px; max-width: min(320px, 35vw); }
.operations-indicator__content { display: flex; flex-direction: column; gap: 3px; min-width: 0; width: 100%; }
.operations-indicator__caption { display: flex; align-items: center; gap: 6px; min-width: 0; }
.operations-indicator__caption > span:first-of-type { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
