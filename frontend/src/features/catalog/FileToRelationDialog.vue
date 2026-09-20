<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppFileInput,
  AppInput,
  AppSection,
  AppSelect,
  AppTable,
  AppToggle,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { columnTally, filenameStem, readDelimited } from "./delimitedFile"

interface Mapping {
  source: string
  target: string
  include: boolean
}

const props = defineProps<{
  modelValue: boolean
  connectorId: string
  initialSchema: string
  running: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  run: [value: { nodeId: string; file: File; params: Record<string, unknown> }]
}>()

const file = ref<File | null>(null)
const schemas = ref<{ label: string; value: string }[]>([])
const schemaMode = ref<"existing" | "new">("existing")
const schemaName = ref(props.initialSchema)
const tableName = ref("")
const mappings = ref<Mapping[]>([])
const preview = ref<string[][]>([])
const trouble = ref("")

const selected = computed(() => mappings.value.filter((mapping) => mapping.include))
/** Columns that would be created without a name to create them under. */
const unnamed = computed(
  () => selected.value.filter((mapping) => mapping.target.trim() === "").length
)

const tally = computed(() =>
  columnTally(mappings.value.length, selected.value.length, unnamed.value)
)
const ready = computed(
  () =>
    file.value !== null &&
    schemaName.value.trim() !== "" &&
    tableName.value.trim() !== "" &&
    selected.value.length > 0 &&
    selected.value.every((mapping) => mapping.target.trim() !== "")
)
const tableRows = computed(() =>
  preview.value.map((row, index) => ({
    index,
    ...Object.fromEntries(
      mappings.value.map((mapping, at) => [mapping.source, row[at]])
    ),
  }))
)
const tableColumns = computed(() =>
  selected.value.map((mapping) => ({
    name: mapping.source,
    label: mapping.target,
    field: mapping.source,
    align: "left" as const,
  }))
)

onMounted(async () => {
  try {
    const answer = await ConnectorsService.readCatalog({
      path: { connector_id: props.connectorId },
      query: {},
    })
    schemas.value = answer.data
      .filter((node) => node.kind === "schema" && node.is_system !== true)
      .map((node) => ({ label: node.name, value: node.id }))
    if (!schemas.value.some((schema) => schema.value === schemaName.value)) {
      schemaName.value = schemas.value[0]?.value ?? ""
    }
  } catch (cause) {
    trouble.value = messageOf(cause, "Could not read the schemas")
  }
})

watch(file, async (chosen) => {
  if (chosen === null) return
  trouble.value = ""
  tableName.value = filenameStem(chosen.name)
  try {
    const parsed = await readDelimited(chosen)
    mappings.value = parsed.columns.map((column) => ({
      source: column,
      target: column,
      include: true,
    }))
    preview.value = parsed.preview
  } catch (cause) {
    mappings.value = []
    preview.value = []
    trouble.value = cause instanceof Error ? cause.message : "Could not read that file"
  }
})

watch(schemaMode, (mode) => {
  schemaName.value = mode === "existing" ? schemas.value[0]?.value ?? "" : ""
})

function run() {
  if (!ready.value || file.value === null) return
  emit("run", {
    nodeId: props.initialSchema,
    file: file.value,
    params: {
      name: tableName.value.trim(),
      schema_name: schemaName.value.trim(),
      create_schema: schemaMode.value === "new",
      columns: selected.value.map(({ source, target }) => ({
        source,
        target: target.trim(),
      })),
    },
  })
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    title="Create table from file"
    subtitle="Choose the destination and the columns before anything is created"
    size="lg"
    data-testid="file-to-relation-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
      >
        {{ error }}
      </AppBanner>
      <AppBanner
        v-if="trouble"
        tone="warning"
      >
        {{ trouble }}
      </AppBanner>
      <AppFileInput
        v-model="file"
        label="CSV or TSV file"
        accept=".csv,.tsv,text/csv,text/tab-separated-values"
        data-testid="load-file"
      />
      <div class="file-to-relation__destination">
        <AppSelect
          v-model="schemaMode"
          label="Schema choice"
          :options="[
            { label: 'Existing schema', value: 'existing' },
            { label: 'Create new schema', value: 'new' },
          ]"
          data-testid="load-schema-mode"
        />
        <AppSelect
          v-if="schemaMode === 'existing'"
          v-model="schemaName"
          label="Schema"
          :options="schemas"
          data-testid="load-schema"
        />
        <AppInput
          v-else
          v-model="schemaName"
          label="New schema"
          data-testid="load-new-schema"
        />
        <AppInput
          v-model="tableName"
          label="Table name"
          data-testid="field-name"
        />
      </div>
      <AppBanner
        v-if="schemaMode === 'new'"
        tone="info"
      >
        The database may refuse this if the connection is not allowed to create schemas.
      </AppBanner>
      <div
        v-if="mappings.length"
        class="file-to-relation__columns"
        data-testid="load-columns"
      >
        <div class="file-to-relation__legend">
          <span>In the file</span>
          <span aria-hidden="true" />
          <span>Column in the new table</span>
          <span
            class="file-to-relation__tally"
            :class="{ 'file-to-relation__tally--wrong': unnamed > 0 }"
            data-testid="load-tally"
          >{{ tally }}</span>
        </div>
        <div
          v-for="mapping in mappings"
          :key="mapping.source"
          class="file-to-relation__row"
          :class="{ 'file-to-relation__row--out': !mapping.include }"
          :data-testid="`load-column-${mapping.source}`"
        >
          <AppToggle
            v-model="mapping.include"
            :label="mapping.source"
          />
          <q-icon
            name="arrow_forward"
            size="16px"
            class="file-to-relation__arrow"
            aria-hidden="true"
          />
          <!-- No visible label: the legend above the block says what this
               column is, and repeating it on every row was most of what made
               the pairing hard to read. Named for a screen reader all the
               same, and by the column it renames rather than by its job.
               Compact, so a file of forty columns is forty short rows; what a
               compact field has no room to say is said once in the legend. -->
          <AppInput
            v-model="mapping.target"
            :aria-label="`Name in the table for ${mapping.source}`"
            :disable="!mapping.include"
            compact
          />
        </div>
      </div>
      <AppTable
        v-if="selected.length && preview.length"
        :rows="tableRows"
        :columns="tableColumns"
        row-key="index"
        compact
        :paged="false"
      />
    </AppSection>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        label="Create table"
        :disable="!ready"
        :loading="running"
        data-testid="load-create"
        @click="run"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.file-to-relation__destination {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--dp-space-3);
}

/* One pair to a row, and the same three columns in the legend above them, so
   the eye reads each mapping left to right. Two pairs to a row fitted more on
   the screen and left it ambiguous which name belonged to which — the whole
   complaint about this dialog. */
.file-to-relation__columns {
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  padding: var(--dp-space-2) var(--dp-space-3);
}

.file-to-relation__legend,
.file-to-relation__row {
  display: grid;
  grid-template-columns: minmax(140px, 1fr) 24px minmax(160px, 1.4fr);
  align-items: center;
  gap: var(--dp-space-2);
}

.file-to-relation__legend {
  grid-template-columns: minmax(140px, 1fr) 24px minmax(160px, 1.4fr) auto;
  padding-bottom: var(--dp-space-1);
  border-bottom: 1px solid var(--dp-border-faint);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--dp-text-muted);
}

.file-to-relation__tally {
  letter-spacing: 0;
  text-transform: none;
  font-weight: 400;
}

.file-to-relation__tally--wrong { color: var(--dp-content-error); }

.file-to-relation__row {
  padding: var(--dp-space-1) 0;
}

.file-to-relation__row + .file-to-relation__row {
  border-top: 1px solid var(--dp-border-faint);
}

.file-to-relation__arrow { color: var(--dp-text-faint); justify-self: center; }

/* A column left out stays in place rather than disappearing: which columns the
   file has is part of what this screen says. */
.file-to-relation__row--out { opacity: 0.55; }
.file-to-relation__row--out .file-to-relation__arrow { visibility: hidden; }
</style>
