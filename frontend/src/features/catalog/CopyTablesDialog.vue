<script setup lang="ts">
import { keepPreviousData, useQuery } from "@tanstack/vue-query"
import { computed, onBeforeUnmount, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import type { TablesChoice } from "@/client"
import { useCatalogLoader } from "@/features/catalog/api"
import type { CrossPasteIntent } from "@/features/catalog/pasteOffers"
import {
  choiceOf,
  copyScript,
  leftBehind,
  originNote,
  runChoice,
  startingPlace,
} from "@/features/catalog/tablesCopy"
import type { CopyChoices, LinksChoice, RowsChoice } from "@/features/catalog/tablesCopy"
import CodeFence from "@/features/content/markdown/CodeFence.vue"
import { placesIn } from "@/features/grid/relationPlaces"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppForm,
  AppInput,
  AppPairs,
  AppPairsRow,
  AppRadioGroup,
  AppSelect,
  AppSpinner,
} from "@/shared/ui"
import type { RadioOption } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * Tables copied with their structure, chosen before anything runs (D182).
 *
 * Every change of a choice asks the server to plan the copy again, and what
 * it answers is all this shows: which tables go, what their links bring, what
 * is left behind and every statement. Nothing runs before Copy.
 *
 * The schema is chosen here, whatever the catalog had selected when Paste was
 * pressed; where it stood is only where the choice starts.
 */
const props = defineProps<{
  intent: CrossPasteIntent
  running: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  run: [copy: { choice: TablesChoice; place: string }]
}>()

const loadChildren = useCatalogLoader()
/** The schemas of the destination, through the catalog's own cache. */
const places = useQuery({
  queryKey: computed(() => ["copy-tables-places", props.intent.destinationConnectorId]),
  queryFn: async () =>
    placesIn((await loadChildren(props.intent.destinationConnectorId, null)).nodes, "")
      .filter((place) => place.kind === "schema"),
})
const place = ref<string | null>(null)
watch(
  () => places.data.value,
  (found) => {
    if (place.value === null && found !== undefined) {
      place.value = startingPlace(found, props.intent.destinationNodeId)
    }
  },
  { immediate: true }
)

/** Names as typed; the plan follows them once typing pauses. */
const typed = ref<Record<string, string>>({})
const names = ref<Record<string, string>>({})
const rows = ref<RowsChoice>("rows")
const links = ref<LinksChoice | null>(null)
const also = ref<string[]>([])
const sqlShown = ref(false)

let pause: ReturnType<typeof setTimeout> | undefined
watch(
  typed,
  (value) => {
    clearTimeout(pause)
    pause = setTimeout(() => (names.value = { ...value }), 300)
  },
  { deep: true }
)
onBeforeUnmount(() => clearTimeout(pause))

const choices = computed<CopyChoices>(() => ({
  names: names.value,
  rows: rows.value,
  links: links.value,
  also: also.value,
}))

const preview = useQuery({
  queryKey: computed(() => [
    "tables-copy",
    props.intent.sourceConnectorId,
    props.intent.sourceNodeIds,
    props.intent.destinationConnectorId,
    place.value,
    choiceOf(choices.value),
  ]),
  enabled: computed(() => place.value !== null),
  // The last plan stays on screen while the next is asked for, so a choice
  // does not blank the window it was made in.
  placeholderData: keepPreviousData,
  retry: false,
  queryFn: async () =>
    (await ConnectorsService.pasteTablesPreview({
      path: { connector_id: props.intent.destinationConnectorId },
      body: {
        source_connector_id: props.intent.sourceConnectorId,
        source_node_ids: props.intent.sourceNodeIds,
        mode: props.intent.mode,
        destination_node_id: place.value,
        target_node_id: props.intent.targetNodeId,
        tables: choiceOf(choices.value),
      },
    })).data,
})

const plan = computed(() => preview.data.value ?? null)
const failure = computed(() => {
  if (props.error) return props.error
  if (places.isError.value) return messageOf(places.error.value, "Could not read the schemas here")
  if (places.data.value?.length === 0) return "This connection has no schema to copy tables into"
  return preview.isError.value ? messageOf(preview.error.value, "The copy could not be planned") : ""
})

/**
 * Shown once there is something to show. The first plan usually arrives in a
 * fraction of a second, and a window opened before it flashed empty; one
 * that is slower opens anyway, saying it is planning.
 */
const shown = ref(false)
const patience = setTimeout(() => (shown.value = true), 400)
watch(
  [plan, failure],
  ([planned, failed]) => {
    if (planned !== null || failed !== "") shown.value = true
  },
  { immediate: true }
)
onBeforeUnmount(() => clearTimeout(patience))
const behind = computed(() => (plan.value === null ? [] : leftBehind(plan.value)))
const script = computed(() => (plan.value === null ? "" : copyScript(plan.value)))
const ready = computed(
  () =>
    plan.value !== null &&
    plan.value.problems.length === 0 &&
    !preview.isPlaceholderData.value &&
    !preview.isFetching.value
)

const ROWS: RadioOption[] = [
  { label: "Structure and rows", value: "rows" },
  { label: "Structure only", value: "structure", description: "Empty tables with every key, index and link" },
]
const linkOptions = computed<RadioOption[]>(() => [
  {
    label: "Copy those tables too",
    value: "copy",
    description: "And the tables they point at, to the end of the chain",
  },
  { label: "Drop the links", value: "drop", description: "The copies point at nothing" },
  ...(plan.value?.keep_allowed === true
    ? [{
        label: "Keep the links to the originals",
        value: "keep",
        description: "The copies point at the tables that are already here",
      }]
    : []),
])

function nameOf(nodeId: string, planned: string): string {
  return typed.value[nodeId] ?? planned
}

function rename(nodeId: string, value: string | number | null) {
  typed.value = { ...typed.value, [nodeId]: String(value ?? "") }
}

function chooseLinks(value: string) {
  links.value = value as LinksChoice
}

function chooseRows(value: string) {
  rows.value = value as RowsChoice
}

function toggleAlso(nodeId: string, on: boolean) {
  also.value = on ? [...also.value, nodeId] : also.value.filter((one) => one !== nodeId)
}

function choosePlace(value: unknown) {
  if (typeof value === "string") place.value = value
}

function copy() {
  const current = plan.value
  if (current === null || place.value === null || !ready.value || props.running) return
  emit("run", {
    choice: runChoice({ ...choices.value, names: { ...names.value, ...typed.value } }, current),
    place: place.value,
  })
}
</script>

<template>
  <WindowDialog
    :model-value="shown"
    title="Copy tables"
    :subtitle="`From ${intent.sourceLabel}`"
    size="wide-form"
    sizing="stable"
    data-testid="copy-tables"
    @update:model-value="emit('close')"
  >
    <AppForm layout="section">
      <AppBanner
        v-if="failure"
        tone="error"
        data-testid="copy-tables-error"
      >
        {{ failure }}
      </AppBanner>
      <AppSelect
        :model-value="place"
        :options="places.data.value ?? []"
        label="Into schema"
        :loading="places.isFetching.value"
        data-testid="copy-tables-place"
        @update:model-value="choosePlace"
      />
      <div
        v-if="plan === null && !failure"
        class="copy-tables__planning"
      >
        <AppSpinner />
        <span>Planning the copy</span>
      </div>
      <AppBanner
        v-for="problem in plan?.problems ?? []"
        :key="`${problem.node_id}-${problem.message}`"
        tone="error"
        data-testid="copy-tables-problem"
      >
        {{ problem.message }}
      </AppBanner>

      <AppPairs
        v-if="plan"
        data-testid="copy-tables-names"
      >
        <template #from>
          Table
        </template>
        <template #to>
          Copy
        </template>
        <AppPairsRow
          v-for="table in plan.tables"
          :key="table.node_id"
          :data-testid="`copy-tables-table-${table.node_id}`"
        >
          <template #from>
            <span class="copy-tables__table">
              <span>{{ table.label }}</span>
              <span
                v-if="originNote(table)"
                class="copy-tables__note"
              >{{ originNote(table) }}</span>
            </span>
          </template>
          <template #to>
            <AppInput
              :model-value="nameOf(table.node_id, table.name)"
              :aria-label="`Name of the copy of ${table.label}`"
              autocomplete="off"
              compact
              :data-testid="`copy-tables-name-${table.node_id}`"
              @update:model-value="rename(table.node_id, $event)"
            />
          </template>
        </AppPairsRow>
      </AppPairs>

      <AppRadioGroup
        v-if="plan"
        :model-value="rows"
        :options="ROWS"
        label="Rows"
        data-testid="copy-tables-rows"
        @update:model-value="chooseRows"
      />

      <template v-if="plan && plan.outside.length > 0">
        <div
          class="copy-tables__links"
          data-testid="copy-tables-outside"
        >
          <span>These tables point at tables that were not ticked:</span>
          <span
            v-for="link in plan.outside"
            :key="`${link.table}-${link.target}`"
            class="copy-tables__link"
          >{{ link.table }} → {{ link.target }}</span>
        </div>
        <AppRadioGroup
          :model-value="links ?? plan.links"
          :options="linkOptions"
          label="Links"
          data-testid="copy-tables-links"
          @update:model-value="chooseLinks"
        />
      </template>

      <div
        v-if="plan && plan.pointing.length > 0"
        class="copy-tables__pointing"
        data-testid="copy-tables-pointing"
      >
        <span>Tables that point at these, to copy as well:</span>
        <AppCheckbox
          v-for="pointing in plan.pointing"
          :key="pointing.node_id"
          :model-value="also.includes(pointing.node_id)"
          :label="`${pointing.label} → ${pointing.points_at.join(', ')}`"
          :data-testid="`copy-tables-also-${pointing.node_id}`"
          @update:model-value="toggleAlso(pointing.node_id, $event)"
        />
      </div>

      <AppBanner
        v-if="behind.length > 0"
        tone="info"
        data-testid="copy-tables-left-behind"
      >
        Not copied:
        <span
          v-for="line in behind"
          :key="line"
          class="copy-tables__line"
        >{{ line }}</span>
      </AppBanner>
      <AppBanner
        v-for="warning in plan?.warnings ?? []"
        :key="warning"
        tone="warning"
      >
        {{ warning }}
      </AppBanner>

      <div
        v-if="plan && script"
        class="copy-tables__sql"
      >
        <AppButton
          variant="quiet"
          size="sm"
          :label="sqlShown ? 'Hide the SQL' : 'Show the SQL'"
          data-testid="copy-tables-sql-toggle"
          @click="sqlShown = !sqlShown"
        />
        <CodeFence
          v-if="sqlShown"
          language="sql"
          :code="script"
        />
      </div>
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        :disable="running"
        @click="emit('close')"
      />
      <AppButton
        label="Copy"
        :disable="!ready"
        :loading="running || (preview.isFetching.value && !plan)"
        data-testid="copy-tables-run"
        @click="copy"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.copy-tables__table {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.copy-tables__note,
.copy-tables__link,
.copy-tables__line {
  color: var(--dp-text-muted);
}
.copy-tables__links,
.copy-tables__pointing,
.copy-tables__sql {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}
.copy-tables__line {
  display: block;
}
.copy-tables__planning {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  color: var(--dp-text-muted);
}
.copy-tables__sql {
  align-items: stretch;
}
.copy-tables__sql > :first-child {
  align-self: flex-start;
}
</style>
