<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { LogEntry } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { useCurrentUser } from "@/shared/auth/currentUser"
import { copyText } from "@/shared/clipboard"
import {
  AppBanner,
  AppButton,
  AppCopyButton,
  AppEmptyState,
  AppIconButton,
  AppInput,
  AppSelect,
  AppSpinner,
  AppToggle,
  AppToolbarRule,
  appIcons,
  toneText,
  useToast,
} from "@/shared/ui"

import { useLogs } from "./api"
import type { LevelChoice, LogFilter, ProcessChoice } from "./api"
import { textOf, timeOf, toneOf } from "./entries"

/**
 * The server's log, a tool of the panel at the foot of the screen (D143,
 * D184): what the backend and the metrics collector wrote, newest first. A
 * superuser's: it names every request and every failure of the installation.
 */
const LEVELS: { label: string; value: LevelChoice }[] = [
  { label: "Everything", value: "all" },
  { label: "Warnings and errors", value: "warning" },
  { label: "Errors", value: "error" },
]
const PROCESSES: { label: string; value: ProcessChoice }[] = [
  { label: "Backend and metrics", value: "all" },
  { label: "Backend", value: "backend" },
  { label: "Metrics", value: "metrics" },
]

const me = useCurrentUser()
const allowed = computed(() => me.data.value?.is_superuser === true)
const toast = useToast()

const level = ref<LevelChoice>("all")
const process = ref<ProcessChoice>("all")
const search = ref("")
// Typed words are asked for once the typing stops, not at every key.
const text = ref("")
let pause: ReturnType<typeof setTimeout> | undefined
watch(search, (value) => {
  clearTimeout(pause)
  pause = setTimeout(() => { text.value = value }, 300)
})
const follow = ref(true)

const filter = computed<LogFilter>(() => ({
  level: level.value,
  process: process.value,
  text: text.value,
}))
const logs = useLogs(filter, { follow, enabled: allowed })
const entries = computed(() => (logs.data.value?.pages ?? []).flatMap((page) => page.entries))
const kept = computed(() => logs.data.value?.pages[0]?.kept ?? true)

// Which entries are open, by what identifies one: two lines of one process
// never share a microsecond.
const open = ref(new Set<string>())
const keyOf = (entry: LogEntry) => `${entry.process} ${entry.time}`
function toggle(entry: LogEntry) {
  const next = new Set(open.value)
  if (!next.delete(keyOf(entry))) next.add(keyOf(entry))
  open.value = next
}

async function copy(entry: LogEntry) {
  try {
    await copyText(textOf(entry))
    toast.info("Copied")
  } catch {
    toast.error("The browser did not allow copying")
  }
}
</script>

<template>
  <div
    class="logs-tool"
    data-testid="logs-tool"
  >
    <AppEmptyState
      v-if="!allowed"
      :icon="appIcons.receiptLong"
      text="Only a superuser can read the server's log."
    />
    <template v-else>
      <div class="logs-tool__bar">
        <AppSelect
          v-model="level"
          :options="LEVELS"
          compact
          class="logs-tool__choice"
          data-testid="logs-level"
        />
        <AppSelect
          v-model="process"
          :options="PROCESSES"
          compact
          class="logs-tool__choice"
          data-testid="logs-process"
        />
        <AppInput
          v-model="search"
          placeholder="Search the text, a ref or a path"
          compact
          clearable
          class="logs-tool__search"
          data-testid="logs-search"
        />
        <AppToolbarRule />
        <AppToggle
          v-model="follow"
          label="Follow"
          data-testid="logs-follow"
        />
        <AppIconButton
          :icon="appIcons.refresh"
          tooltip="Read the log again"
          data-testid="logs-reload"
          @click="logs.refetch()"
        />
      </div>

      <div
        class="logs-tool__body"
        data-testid="logs-body"
      >
        <AppSpinner v-if="logs.isPending.value" />
        <AppBanner
          v-else-if="logs.isError.value"
          tone="error"
        >
          {{ messageOf(logs.error.value, "The log could not be read") }}
        </AppBanner>
        <AppEmptyState
          v-else-if="!kept"
          :icon="appIcons.receiptLong"
          text="This server keeps no log files. Set LOG_DIR to keep them; until then the log is on the server's standard output."
        />
        <AppEmptyState
          v-else-if="entries.length === 0"
          :icon="appIcons.receiptLong"
          text="Nothing in the log matches."
        />
        <template v-else>
          <div
            v-for="entry in entries"
            :key="keyOf(entry)"
            class="logs-tool__entry"
            :class="{ 'logs-tool__entry--open': open.has(keyOf(entry)) }"
            :data-testid="`log-entry-${entry.level}`"
          >
            <button
              type="button"
              class="logs-tool__line"
              :aria-expanded="open.has(keyOf(entry))"
              :title="entry.time"
              @click="toggle(entry)"
            >
              <span class="logs-tool__time">{{ timeOf(entry) }}</span>
              <span
                class="logs-tool__level"
                :class="toneOf(entry) === null ? 'logs-tool__muted' : toneText(toneOf(entry) ?? 'info')"
              >{{ entry.level }}</span>
              <span class="logs-tool__process logs-tool__muted">{{ entry.process }}</span>
              <span class="logs-tool__logger logs-tool__muted">{{ entry.logger }}</span>
              <span
                class="logs-tool__message"
                :class="toneOf(entry) === null ? '' : toneText(toneOf(entry) ?? 'info')"
              >{{ entry.message }}</span>
              <span
                v-if="entry.ref"
                class="logs-tool__ref"
                data-testid="log-entry-ref"
              >ref {{ entry.ref }}</span>
            </button>
            <div
              v-if="open.has(keyOf(entry))"
              class="logs-tool__details"
              data-testid="log-entry-details"
            >
              <div class="logs-tool__facts">
                <span>{{ entry.time }}</span>
                <span v-if="entry.request">{{ entry.request }}</span>
                <span v-if="entry.ref">ref {{ entry.ref }}</span>
                <AppCopyButton
                  tooltip="Copy this entry"
                  data-testid="log-entry-copy"
                  @click="copy(entry)"
                />
              </div>
              <pre class="logs-tool__text">{{ entry.message }}</pre>
              <pre
                v-if="entry.exception"
                class="logs-tool__text"
                data-testid="log-entry-exception"
              >{{ entry.exception }}</pre>
            </div>
          </div>
          <div
            v-if="logs.hasNextPage.value"
            class="logs-tool__older"
          >
            <AppButton
              variant="quiet"
              label="Older entries"
              :loading="logs.isFetchingNextPage.value"
              data-testid="logs-older"
              @click="logs.fetchNextPage()"
            />
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.logs-tool {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.logs-tool__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: 0 var(--dp-space-2) var(--dp-space-2) 0;
  border-bottom: 1px solid var(--dp-border);
}
.logs-tool__choice {
  flex: 0 1 200px;
  min-width: 0;
}
.logs-tool__search {
  flex: 0 1 320px;
  min-width: 0;
}
.logs-tool__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: var(--dp-space-2);
  overscroll-behavior: contain;
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-mono);
  line-height: var(--dp-line-height-mono);
}
.logs-tool__entry--open {
  background: var(--dp-hover);
}
/* One line per entry, the message cut where the panel ends. */
.logs-tool__line {
  display: flex;
  align-items: baseline;
  gap: var(--dp-space-2);
  width: 100%;
  padding: var(--dp-space-half) var(--dp-space-1);
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.logs-tool__line:hover {
  background: var(--dp-hover);
}
.logs-tool__line:focus-visible {
  outline: 2px solid var(--dp-focus-border);
  outline-offset: calc(-1 * var(--dp-space-half));
}
.logs-tool__time,
.logs-tool__level,
.logs-tool__process,
.logs-tool__ref {
  flex: none;
}
.logs-tool__level {
  width: 8ch;
}
.logs-tool__process {
  width: 8ch;
}
.logs-tool__logger {
  flex: 0 1 28ch;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.logs-tool__message {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.logs-tool__muted {
  color: var(--dp-text-muted);
}
.logs-tool__ref {
  color: var(--dp-text-muted);
}
.logs-tool__details {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  padding: var(--dp-space-1) var(--dp-space-2) var(--dp-space-2);
}
.logs-tool__facts {
  display: flex;
  align-items: center;
  gap: var(--dp-space-3);
  color: var(--dp-text-muted);
}
.logs-tool__text {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.logs-tool__older {
  display: flex;
  justify-content: center;
  padding: var(--dp-space-2);
}
</style>
