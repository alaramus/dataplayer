<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import type { ExplainResult } from "@/client"
import { estimate, flatten, nodeById, share } from "@/features/queries/explain"
import { AppBanner, AppButton, AppIconButton } from "@/shared/ui"

/**
 * A plan in the three views D65 asks for, showing one selection: the source's
 * own tree, that tree read as a list, and what the server prints. All three
 * address an operation by the same id.
 *
 * Everything here is an estimate. Nothing was run, and the screen says so
 * rather than letting cost figures look like measurements.
 */

const props = defineProps<{ plan: ExplainResult }>()
const emit = defineEmits<{ close: [] }>()

const showing = ref<"tree" | "table" | "raw">("tree")
const chosen = ref<string>("0")

const rows = computed(() => flatten(props.plan.plan))
const selected = computed(() => nodeById(props.plan.plan, chosen.value))
const details = computed(() => Object.entries(selected.value?.details ?? {}))
</script>

<template>
  <div
    class="explain"
    data-testid="explain-view"
  >
    <div class="explain__bar">
      <AppButton
        v-for="view in ['tree', 'table', 'raw'] as const"
        :key="view"
        :variant="showing === view ? 'current' : 'quiet'"
        size="sm"
        :label="view === 'raw' ? 'Raw plan' : view === 'tree' ? 'Tree' : 'Table'"
        :data-testid="`explain-${view}`"
        @click="showing = view"
      />
      <span class="explain__note">
        Estimated: nothing was run.
        <template v-if="plan.total_cost !== null">
          Cost {{ plan.total_cost?.toFixed(2) }}
        </template>
        <template v-if="plan.rows !== null"> · {{ plan.rows }} rows</template>
      </span>
      <AppIconButton
        :icon="appIcons.close"
        tooltip="Back to the results"
        data-testid="explain-close"
        @click="emit('close')"
      />
    </div>

    <AppBanner
      v-if="plan.truncated"
      tone="warning"
      class="explain__banner"
      data-testid="explain-truncated"
    >
      This plan has more operations than are shown here.
    </AppBanner>

    <div class="explain__body">
      <div
        v-if="showing === 'raw'"
        class="explain__raw"
        data-testid="explain-raw-plan"
      >
        <pre>{{ plan.raw }}</pre>
      </div>

      <div
        v-else
        class="explain__list"
        :data-view="showing"
      >
        <button
          v-for="row in rows"
          :key="row.id"
          type="button"
          class="explain__row"
          :class="{ 'explain__row--chosen': row.id === chosen }"
          :style="
            showing === 'tree' ? { paddingInlineStart: `${8 + row.depth * 16}px` } : undefined
          "
          :data-testid="`explain-node-${row.id}`"
          @click="chosen = row.id"
        >
          <span
            class="explain__share"
            :style="{ width: `${share(row.node, plan.total_cost) * 100}%` }"
          />
          <span class="explain__label">{{ row.node.label }}</span>
          <span class="explain__estimate">{{ estimate(row.node) }}</span>
        </button>
      </div>

      <aside
        v-if="showing !== 'raw' && selected !== null"
        class="explain__details"
        data-testid="explain-details"
      >
        <h3 class="explain__heading">
          {{ selected.label }}
        </h3>
        <p
          v-if="details.length === 0"
          class="explain__detail"
        >
          The source said nothing else about this operation.
        </p>
        <p
          v-for="[key, value] in details"
          :key="key"
          class="explain__detail"
        >
          <span class="explain__detail-name">{{ key }}</span>
          {{ value }}
        </p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.explain {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.explain__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-half) var(--dp-space-1);
  border-bottom: 1px solid var(--dp-border-faint);
}
.explain__note {
  flex: 1;
  overflow: hidden;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
  white-space: nowrap;
  text-overflow: ellipsis;
}
.explain__banner {
  flex: none;
  margin: var(--dp-space-2);
}
.explain__body {
  flex: 1;
  min-height: 0;
  display: flex;
}
.explain__list {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: var(--dp-space-1) 0;
}
.explain__row {
  position: relative;
  display: flex;
  align-items: baseline;
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
.explain__row:hover {
  background: var(--dp-hover);
}
.explain__row--chosen {
  border-inline-start-color: var(--dp-link);
  background: var(--dp-selected-quiet);
}
/* How much of the plan's estimated cost this operation carries, behind the
   row rather than as another column to read. */
.explain__share {
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  background: var(--dp-selected-quiet);
  pointer-events: none;
}
.explain__label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.explain__estimate {
  flex: none;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
}
.explain__details {
  flex: none;
  width: 280px;
  overflow: auto;
  padding: var(--dp-space-2) var(--dp-space-2);
  border-inline-start: 1px solid var(--dp-border-faint);
}
.explain__heading {
  margin: 0 0 var(--dp-space-2);
  font-size: var(--dp-font-size-sm);
  font-weight: 600;
}
.explain__detail {
  margin: 0 0 var(--dp-space-2);
  font-size: var(--dp-font-size-xs);
  word-break: break-word;
}
.explain__detail-name {
  display: block;
  color: var(--dp-text-muted);
}
.explain__raw {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--dp-space-2) var(--dp-space-3);
}
.explain__raw pre {
  margin: 0;
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-sm);
}
</style>
