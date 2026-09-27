<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { computed, onBeforeUnmount, ref, watch } from "vue"

import type { JobPublic } from "@/client"
import { connectorsKey, useConnectors } from "@/features/connectors/api"
import { backupsKey, servicesKey, useCancelJob, useServices } from "@/features/services/api"
import { messageOf } from "@/shared/api/errors"
import { notices } from "@/shared/notifications"
import { isActive, useOperations } from "@/shared/operations"
import { AppBadge, AppButton, AppProgress, AppTooltip, useToast } from "@/shared/ui"
import { useWindowManager } from "@/shared/windows"
import { useSourceChangesStore } from "@/stores/sourceChanges"
import ActivityPanel from "./ActivityPanel.vue"
import { jobsKey, useJobs } from "./api"
import { createDismissedJobs } from "./dismissed"
import {
  arrivals, endedEntry, endings, isRecent, jobOfEnding, linesBeyond, toldOnScreen,
} from "./endings"
import { pipelineWriting } from "./pipelineRuns"
import { foreground, jobTitle, localRow, serverRow } from "./presentation"
import type { ProcessRow } from "./presentation"
import { useAttention } from "./sources"
import { sourceDataKeys, touchedSources } from "./sourceOperations"
import {
  createRereader, startedHere, toldInThisTab, transferChanges, transferWriting,
} from "./transfers"

/**
 * The bell at the end of the status bar, and the sheet it opens (D113).
 *
 * It says the most urgent true thing: while something runs, its step and
 * progress stand beside the bell, and the bell carries how much is waiting.
 * The count is what is waiting and what is working, never how much has been
 * said — a badge that counts every "Copied" is a badge nobody reads. Red when
 * somebody has to answer, blue when things are only running.
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
const dismissed = createDismissedJobs()
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

// Every settled target of a source operation may have changed what its
// connection reads, so each one re-reads that connection's data (D123).
let sourceSignatures = new Map<string, string>()
watch(serverJobs, (listed) => {
  const { seen, connectorIds } = touchedSources(sourceSignatures, listed)
  sourceSignatures = seen
  for (const connectorId of connectorIds) {
    for (const queryKey of sourceDataKeys(connectorId)) {
      void queryClient.invalidateQueries({ queryKey })
    }
  }
})

// A transfer re-reads the catalogs it writes into as files arrive, at most
// every two seconds, and the tab that started it says how it ended (D168).
// A pipeline's run does the same as its links end (D177).
const changes = useSourceChangesStore()
const rereader = createRereader((connectorId) => { changes.announce(connectorId) })
onBeforeUnmount(() => { rereader.dispose() })
let transferSignatures = new Map<string, string>()
watch([serverJobs, startedHere], ([listed, started]) => {
  const { seen, touched, ended } = transferChanges(
    transferSignatures, listed, started, (job) => transferWriting(job) ?? pipelineWriting(job)
  )
  transferSignatures = seen
  for (const { connectorId, settled } of touched) rereader.reread(connectorId, settled)
  // What it ended as is told below, with every other job's ending (D181).
  for (const job of ended) toldInThisTab(job.id)
  if (touched.some((change) => change.settled)) {
    for (const queryKey of [["paste-offers"], ["pair-offers"], ["clipboard-offer"]]) {
      void queryClient.invalidateQueries({ queryKey })
    }
  }
})
// A transfer just started is read at once rather than at the next poll.
watch(startedHere, () => { void queryClient.invalidateQueries({ queryKey: jobsKey }) })

function subjectOf(kind: string, subjectId: string | null): string | undefined {
  if (subjectId === null) return undefined
  return kind.startsWith("service.")
    ? services.data.value?.find((service) => service.id === subjectId)?.connector_name
    : connectors.data.value?.data.find((connector) => connector.id === subjectId)?.name
}

function rowOf(job: JobPublic) {
  return serverRow(job, subjectOf(job.kind, job.subject_id))
}

/**
 * What runs, and nothing else (D181): an ended job is one entry in Recent or
 * Needs you, and a local operation's ending is said by whoever started it.
 */
const rows = computed(() => [
  ...operations.items.value.map(localRow),
  ...serverJobs.value.map(rowOf),
].filter((row) => row.active).sort((a, b) => b.createdAt - a.createdAt))

const attention = useAttention(
  {
    answerAccess: (connectorId) => { emit("answerAccess", connectorId) },
    openConnection: (connectorId) => { emit("openConnection", connectorId) },
  },
  serverJobs,
  (job) => {
    const subject = subjectOf(job.kind, job.subject_id)
    return {
      label: `${jobTitle(job)}${subject ? ` · ${subject}` : ""}`,
      lines: linesBeyond(rowOf(job).detail, job.message ?? ""),
    }
  },
  dismissed
)

/**
 * Every ending, recorded once (D181). One that happens while this tab watches
 * — a job it saw running, or started a moment ago — puts its card up; one
 * found already over, after a reload or ended elsewhere, is only recorded.
 * A failure is not recorded here: it waits in Needs you, and arrives there.
 */
let watchedJobs = new Set<string>()
// Taken the moment a job is started here, before any poll: the watcher above
// forgets it as soon as it ends, and a job that ends before it is ever seen
// running is still one this tab was waiting for.
watch(startedHere, (started) => {
  watchedJobs = new Set([...watchedJobs, ...started])
}, { immediate: true, flush: "sync" })
watch(serverJobs, (listed) => {
  const { watched, ended } = endings(watchedJobs, listed)
  watchedJobs = watched
  for (const job of ended) recordEnding(job, toldOnScreen(job))
  const now = Date.now()
  for (const job of listed) if (isRecent(job, now)) recordEnding(job, false)
}, { immediate: true })

function recordEnding(job: JobPublic, card: boolean) {
  if (dismissed.ids.value.has(job.id)) return
  const entry = endedEntry(job, rowOf(job))
  if (entry !== null) log.record(entry.notice, { id: entry.id, at: entry.at, card })
}

// An ending waved away in Recent stays away after the next poll and reload.
watch(log.forgotten, (ids) => {
  for (const id of ids) {
    const jobId = jobOfEnding(id)
    if (jobId !== null) dismissed.dismiss(jobId)
  }
})

/**
 * A card for what is new in Needs you since the page opened: the thing is
 * recorded there, and the card is only its arrival, so one failure is one
 * entry however it is seen (D181).
 */
const openedAt = Date.now()
let knownAttention = new Set<string>()
watch(attention, (items) => {
  const { known, arrived } = arrivals(knownAttention, items, openedAt)
  knownAttention = known
  for (const item of arrived) {
    log.announce({
      id: `attention:${item.id}`, tone: item.tone, title: item.title, message: item.detail, action: item.action,
    })
  }
}, { immediate: true })

const activeCount = computed(() => operations.items.value.filter(isActive).length +
  (jobs.data.value?.pages[0]?.active_count ?? 0))
/** What the button marks: what is waiting, and what is running. Not the log. */
const count = computed(() => attention.value.length + activeCount.value)
const current = computed(() => foreground(rows.value))
// The bell stays a bell while work runs: the step beside it says that.
const icon = computed(() => {
  if (jobs.isError.value) return "sync_problem"
  return attention.value.length > 0 ? "notifications_active" : "notifications"
})
const tooltip = computed(() => {
  if (jobs.isError.value) return "Activity unavailable. Show activity"
  if (current.value) return `${current.value.status}: ${current.value.detail}. Show activity`
  return "Show activity"
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

</script>

<template>
  <!-- The step grows leftwards from the bell, so the bell itself stays on
       the axis of the right rail buttons. -->
  <span class="activity-indicator-bar">
    <AppButton
      v-if="current"
      variant="quiet"
      size="sm"
      class="activity-indicator__running"
      :aria-expanded="log.open.value"
      data-testid="activity-progress"
      @click="log.setOpen(!log.open.value)"
    >
      <span class="activity-indicator__step">{{ current.brief ?? current.label }}</span>
      <AppProgress
        class="activity-indicator__progress"
        :label="current.brief ?? current.label"
        :value="current.progress"
        :paused="current.paused"
      />
      <AppTooltip>{{ current.status }}: {{ current.detail }}. Show activity</AppTooltip>
    </AppButton>
    <AppButton
      variant="quiet"
      size="sm"
      class="activity-indicator"
      :class="{ 'activity-indicator--error': jobs.isError.value }"
      aria-label="Show activity"
      :aria-expanded="log.open.value"
      data-testid="activity-indicator"
      @click="log.setOpen(!log.open.value)"
    >
      <q-icon :name="icon" />
      <AppBadge
        v-if="count > 0"
        corner
        :label="String(count)"
        :tone="attention.length > 0 ? 'error' : 'info'"
        data-testid="activity-count"
      />
      <AppTooltip>{{ tooltip }}</AppTooltip>
    </AppButton>
  </span>

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
    @more="loadMore"
    @refresh="refresh"
  />
</template>

<style scoped>
.activity-indicator-bar { display: flex; align-items: center; gap: var(--dp-space-1); min-width: 0; }
/* The same 32px target as the rail buttons; the count hangs off its corner. */
.activity-indicator { position: relative; min-width: 32px; min-height: 32px; }
.activity-indicator .q-icon { font-size: 24px; }
.activity-indicator--error .q-icon { color: var(--dp-content-error); }
.activity-indicator__running { position: relative; min-width: 110px; max-width: min(260px, 30vw); }
.activity-indicator__step {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
/* Overlaid: in flow it adds its height to the button and the footer grows (D113). */
.activity-indicator__progress { position: absolute; left: 8px; right: 8px; bottom: 2px; width: auto; }
</style>
