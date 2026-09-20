<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { RunPublic, StatementPublic } from "@/client"
import ResultTable from "@/features/queries/ResultTable.vue"
import { AppBanner, AppEmptyState, AppIconButton } from "@/shared/ui"

/**
 * What a run did, laid out the way D65 asks. An error is an output, not a
 * toast that disappears and not a pretend row in a table.
 *
 * A run may also fail as a whole before any statement ran — the source refused
 * the context, or could not be reached — and that answer belongs to the run
 * rather than to a statement, so it is shown above them all (D77).
 */

const props = withDefaults(
  defineProps<{
    run: RunPublic
    /** This is the run before the one now going, and says so.  */
    stale?: boolean
  }>(),
  { stale: false }
)

const emit = defineEmits<{
  /** Give one captured result a panel of its own. */
  promote: [statement: StatementPublic]
  /** Keep this result on screen when the next run finishes. */
  "toggle-pin": []
}>()

const chosen = ref(0)
const showMessages = ref(false)

// Optional in the schema because a run answers before its statements have
// done anything; empty is the honest reading of that.
const statements = computed(() => props.run.statements ?? [])
const selected = computed<StatementPublic | undefined>(
  () => statements.value.find((statement) => statement.ordinal === chosen.value)
)
/**
 * Everything the run said, in the order it said it.
 *
 * Notices and errors together: a person reading "what happened" wants one
 * chronological list, not two places to look.
 */
const messages = computed(() => [
  ...(props.run.error === null || props.run.error === undefined
    ? []
    : [{ ordinal: -1, severity: "RUN", message: props.run.error }]),
  ...statements.value.flatMap((statement) => [
    ...(statement.notices ?? []).map((notice) => ({
      ordinal: statement.ordinal,
      severity: notice.severity,
      message: notice.message,
    })),
    ...(statement.diagnostic === null || statement.diagnostic === undefined
      ? []
      : [
          {
            ordinal: statement.ordinal,
            severity: statement.diagnostic.category.toUpperCase(),
            message: statement.diagnostic.hint
              ? `${statement.diagnostic.message} — ${statement.diagnostic.hint}`
              : statement.diagnostic.message,
          },
        ]),
  ]),
])

// The first statement that has something to show: an error, or rows.
watch(
  statements,
  (found) => {
    const interesting = found.find(
      (statement) => statement.result_id !== null || statement.diagnostic !== null
    )
    if (interesting !== undefined) chosen.value = interesting.ordinal
  },
  { immediate: true }
)

function label(statement: StatementPublic): string {
  return `${statement.ordinal + 1}. ${statement.kind}`
}

function duration(statement: StatementPublic): string {
  return statement.duration_ms === null || statement.duration_ms === undefined
    ? ""
    : `${statement.duration_ms} ms`
}
</script>

<template>
  <div
    class="run-outcome"
    data-testid="run-outcome"
  >
    <AppBanner
      v-if="run.error"
      tone="error"
      class="run-outcome__error"
      data-testid="run-refusal"
    >
      {{ run.error }}
    </AppBanner>

    <div class="run-outcome__statements">
      <button
        v-for="statement in statements"
        :key="statement.ordinal"
        type="button"
        class="run-outcome__statement"
        :class="{
          'run-outcome__statement--chosen': statement.ordinal === chosen,
        }"
        :data-status="statement.status"
        :data-testid="`run-statement-${statement.ordinal}`"
        @click="chosen = statement.ordinal"
      >
        <span class="run-outcome__label">{{ label(statement) }}</span>
        <span class="run-outcome__status">{{ statement.status }}</span>
        <span class="run-outcome__duration">{{ duration(statement) }}</span>
      </button>
      <button
        type="button"
        class="run-outcome__statement"
        :class="{ 'run-outcome__statement--chosen': showMessages }"
        data-testid="run-messages-tab"
        @click="showMessages = !showMessages"
      >
        <span class="run-outcome__label">Messages</span>
        <span class="run-outcome__status">{{ messages.length }}</span>
      </button>
    </div>

    <div class="run-outcome__output">
      <div
        v-if="showMessages"
        class="run-outcome__messages"
        data-testid="run-messages"
      >
        <AppEmptyState
          v-if="messages.length === 0"
          text="Nothing was said"
        />
        <p
          v-for="(message, index) in messages"
          :key="index"
          class="run-outcome__message"
        >
          <span class="run-outcome__severity">{{ message.severity }}</span>
          {{ message.message }}
        </p>
      </div>

      <template v-else-if="selected !== undefined">
        <AppBanner
          v-if="selected.diagnostic"
          tone="error"
          class="run-outcome__error"
          data-testid="run-error"
        >
          {{ selected.diagnostic.message }}
          <template v-if="selected.diagnostic.hint">
            — {{ selected.diagnostic.hint }}
          </template>
        </AppBanner>

        <div
          v-if="selected.result_id"
          class="run-outcome__result"
        >
          <div class="run-outcome__result-bar">
            <AppIconButton
              icon="push_pin"
              tooltip="Keep this result when the next run finishes"
              data-testid="run-pin"
              @click="emit('toggle-pin')"
            />
            <AppIconButton
              icon="open_in_new"
              tooltip="Open this result in the workspace"
              data-testid="run-promote"
              @click="emit('promote', selected)"
            />
          </div>
          <ResultTable
            :key="selected.result_id"
            :result-id="selected.result_id"
            :stale="stale"
            class="run-outcome__table"
          />
        </div>
        <AppEmptyState
          v-else-if="!selected.diagnostic"
          :text="
            selected.status === 'not_run'
              ? 'This statement was not run'
              : selected.command_tag ?? 'This statement returned no rows'
          "
          data-testid="run-no-rows"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
.run-outcome {
  display: flex;
  height: 100%;
  min-height: 0;
}
.run-outcome__statements {
  flex: none;
  width: 180px;
  overflow: auto;
  border-inline-end: 1px solid var(--dp-border-faint);
}
.run-outcome__statement {
  display: flex;
  gap: var(--dp-space-2);
  width: 100%;
  padding: var(--dp-space-1) var(--dp-space-2);
  border: none;
  border-inline-start: 2px solid transparent;
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}
.run-outcome__statement:hover {
  background: var(--dp-hover);
}
.run-outcome__statement--chosen {
  border-inline-start-color: var(--dp-link);
  background: var(--dp-selected-quiet);
}
.run-outcome__label {
  flex: 1;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.run-outcome__status,
.run-outcome__duration {
  color: var(--dp-text-muted);
  font-size: 11px;
}
.run-outcome__statement[data-status="failed"] .run-outcome__status,
.run-outcome__statement[data-status="timed_out"] .run-outcome__status {
  color: var(--dp-content-error);
}
.run-outcome__output {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.run-outcome__result {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.run-outcome__result-bar {
  flex: none;
  display: flex;
  justify-content: flex-end;
  gap: var(--dp-space-half);
  padding: var(--dp-space-half) var(--dp-space-1) 0;
}
.run-outcome__table {
  flex: 1;
  min-height: 0;
}
.run-outcome__error {
  flex: none;
  margin: var(--dp-space-2);
}
.run-outcome__messages {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--dp-space-2) var(--dp-space-3);
}
.run-outcome__message {
  margin: 0 0 var(--dp-space-2);
  font-family: var(--dp-font-mono);
  font-size: 12px;
}
.run-outcome__severity {
  color: var(--dp-text-muted);
  margin-inline-end: var(--dp-space-2);
}
</style>
