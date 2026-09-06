<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, ref, watch } from "vue"

import { connectorsKey, useConnectors } from "@/features/connectors/api"
import { backupsKey, servicesKey, useCancelJob, useServices } from "@/features/services/api"
import { messageOf } from "@/shared/api/errors"
import { notices } from "@/shared/notifications"
import { isActive, useOperations } from "@/shared/operations"
import { AppButton, AppProgress, AppTooltip, useToast } from "@/shared/ui"
import { useWindowManager } from "@/shared/windows"
import ActivityPanel from "./ActivityPanel.vue"
import { useJobs } from "./api"
import { foreground, JOB_LABELS, localRow, serverRow } from "./presentation"
import type { ProcessRow } from "./presentation"
import { useAttention } from "./sources"

/**
 * The one control at the end of the status bar, and the sheet it opens (D113).
 *
 * It says the most urgent true thing: the step of what is running, if anything
 * is, and otherwise a bell and how much is waiting. The count is what is
 * waiting and what is working, never how much has been said — a badge that
 * counts every "Copied" is a badge nobody reads.
 */
const emit = defineEmits<{
  /** Show the connection's permissions page, where a request is answered. */
  answerAccess: [connectorId: string]
  openConnection: [connectorId: string]
}>()

const jobs = useJobs()
const queryClient = useQueryClient()
const services = useServices()
const connectors = useConnectors()
const operations = useOperations()
const windows = useWindowManager()
const cancel = useCancelJob()
const toast = useToast()
const log = notices()
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

function subjectOf(kind: string, subjectId: string | null): string | undefined {
  if (subjectId === null) return undefined
  return kind.startsWith("service.")
    ? services.data.value?.find((service) => service.id === subjectId)?.connector_name
    : connectors.data.value?.data.find((connector) => connector.id === subjectId)?.name
}

const rows = computed(() => {
  const server = serverJobs.value
    .map((job) => serverRow(job, subjectOf(job.kind, job.subject_id)))
    .filter((row) => row.active || !hidden.value.has(row.id))
  return [...operations.items.value.map(localRow), ...server]
    .sort((a, b) => Number(b.active) - Number(a.active) || b.createdAt - a.createdAt)
})

const attention = useAttention(
  {
    answerAccess: (connectorId) => { emit("answerAccess", connectorId) },
    openConnection: (connectorId) => { emit("openConnection", connectorId) },
  },
  serverJobs,
  (job) => {
    const subject = subjectOf(job.kind, job.subject_id)
    return `${JOB_LABELS[job.kind]}${subject ? ` · ${subject}` : ""}`
  }
)

const activeCount = computed(() => operations.items.value.filter(isActive).length +
  (jobs.data.value?.pages[0]?.active_count ?? 0))
/** What the button marks: what is waiting, and what is running. Not the log. */
const count = computed(() => attention.value.length + activeCount.value)
const current = computed(() => foreground(rows.value))
const caption = computed(() => {
  if (current.value) return current.value.label
  if (jobs.isError.value) return "Activity unavailable"
  return "Activity"
})
const icon = computed(() => {
  if (jobs.isError.value) return "sync_problem"
  if (current.value) return current.value.paused ? "pause" : "pending_actions"
  return attention.value.length > 0 ? "notifications_active" : "notifications"
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

function loadMore() { void jobs.fetchNextPage() }
function refresh() { void jobs.refetch() }

function clearFinished() {
  operations.clearFinished()
  hidden.value = new Set([...hidden.value, ...rows.value.filter((row) => !row.active).map((row) => row.id)])
}
</script>

<template>
  <AppButton
    variant="quiet"
    size="sm"
    class="activity-indicator"
    aria-label="Show activity"
    :aria-expanded="log.open.value"
    data-testid="activity-indicator"
    @click="log.setOpen(!log.open.value)"
  >
    <span class="activity-indicator__content">
      <span class="activity-indicator__caption">
        <q-icon :name="icon" />
        <span>{{ caption }}</span>
        <span
          v-if="count > 0"
          class="activity-indicator__count"
          data-testid="activity-count"
        >{{ count }}</span>
      </span>
      <AppProgress
        v-if="current"
        :label="current.label"
        :value="current.progress"
        :paused="current.paused"
      />
    </span>
    <AppTooltip>{{ current ? `${current.status}: ${current.detail}. ` : '' }}Show activity</AppTooltip>
  </AppButton>

  <ActivityPanel
    v-if="log.open.value"
    :attention="attention"
    :rows="rows"
    :error="error"
    :loading="jobs.isFetching.value"
    :more="jobs.hasNextPage.value"
    :stopping="stopping"
    :bottom="windows.context.bottomInset.value"
    @close="log.setOpen(false)"
    @pause="operations.pause($event.id)"
    @resume="operations.resume($event.id)"
    @stop="stop"
    @clear-finished="clearFinished"
    @more="loadMore"
    @refresh="refresh"
  />
</template>

<style scoped>
.activity-indicator { min-width: 110px; max-width: min(320px, 35vw); }
.activity-indicator__content { display: flex; flex-direction: column; gap: 3px; min-width: 0; width: 100%; }
.activity-indicator__caption { display: flex; align-items: center; gap: 6px; min-width: 0; }
.activity-indicator__caption > span:first-of-type { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.activity-indicator__count {
  flex: none;
  min-width: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--dp-border-strong);
  color: var(--dp-text-strong);
  font-size: 10px;
  line-height: 16px;
  text-align: center;
}
</style>
