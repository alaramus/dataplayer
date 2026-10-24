<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { callsDatabases } from "@/features/catalog/nodes"
import { t } from "@/shared/i18n"
import {
  AppBanner,
  AppButton,
  AppFileInput,
  AppForm,
  AppInput,
  AppPairs,
  AppPairsRow,
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
/** Whether the connection calls its schemas databases, as MySQL does (D229). */
const databases = ref(false)
const WORDS = {
  schemas_failed: ["catalog.file_to_relation.schemas_failed", "catalog.file_to_relation.databases_failed"],
  schema_choice: ["catalog.file_to_relation.schema_choice", "catalog.file_to_relation.database_choice"],
  existing_schema: ["catalog.file_to_relation.existing_schema", "catalog.file_to_relation.existing_database"],
  new_schema_option: ["catalog.file_to_relation.new_schema_option", "catalog.file_to_relation.new_database_option"],
  schema: ["catalog.file_to_relation.schema", "catalog.file_to_relation.database"],
  new_schema: ["catalog.file_to_relation.new_schema", "catalog.file_to_relation.new_database"],
  new_schema_hint: ["catalog.file_to_relation.new_schema_hint", "catalog.file_to_relation.new_database_hint"],
} as const
function word(key: keyof typeof WORDS): string {
  return t(WORDS[key][databases.value ? 1 : 0])
}
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
    databases.value = callsDatabases(answer.data)
    schemas.value = answer.data
      .filter((node) => node.kind === "schema" && node.is_system !== true)
      .map((node) => ({ label: node.name, value: node.id }))
    if (!schemas.value.some((schema) => schema.value === schemaName.value)) {
      schemaName.value = schemas.value[0]?.value ?? ""
    }
  } catch (cause) {
    trouble.value = messageOf(cause, word("schemas_failed"))
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
    trouble.value = cause instanceof Error ? cause.message : t("catalog.file_to_relation.file_failed")
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
    :title="t('catalog.file_to_relation.title')"
    :subtitle="t('catalog.file_to_relation.subtitle')"
    size="wide-form"
    sizing="stable"
    data-testid="file-to-relation-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
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
        :label="t('catalog.action_dialog.file')"
        :hint="t('catalog.file_to_relation.file_hint')"
        accept=".csv,.tsv,text/csv,text/tab-separated-values"
        data-testid="load-file"
      />
      <AppSelect
        v-model="schemaMode"
        :label="word('schema_choice')"
        :options="[
          { label: word('existing_schema'), value: 'existing' },
          { label: word('new_schema_option'), value: 'new' },
        ]"
        data-testid="load-schema-mode"
      />
      <AppSelect
        v-if="schemaMode === 'existing'"
        v-model="schemaName"
        :label="word('schema')"
        :options="schemas"
        data-testid="load-schema"
      />
      <AppInput
        v-else
        v-model="schemaName"
        :label="word('new_schema')"
        :hint="word('new_schema_hint')"
        autocomplete="off"
        data-testid="load-new-schema"
      />
      <AppInput
        v-model="tableName"
        :label="t('catalog.file_to_relation.table_name')"
        autocomplete="off"
        data-testid="field-name"
      />
      <AppPairs
        v-if="mappings.length"
        data-testid="load-columns"
      >
        <template #from>
          {{ t("catalog.file_to_relation.in_file") }}
        </template>
        <template #to>
          {{ t("catalog.file_to_relation.new_column") }}
        </template>
        <template #aside>
          <span
            :class="{ 'file-to-relation__tally--wrong': unnamed > 0 }"
            data-testid="load-tally"
          >{{ tally }}</span>
        </template>
        <AppPairsRow
          v-for="mapping in mappings"
          :key="mapping.source"
          :idle="!mapping.include"
          :data-testid="`load-column-${mapping.source}`"
        >
          <template #from>
            <AppToggle
              v-model="mapping.include"
              :label="mapping.source"
            />
          </template>
          <!-- No visible label: the legend above says what this column is,
               and repeating it on every row was most of what made the pairing
               hard to read. Named for a screen reader all the same, by the
               column it renames rather than by its job. -->
          <template #to>
            <AppInput
              v-model="mapping.target"
              :aria-label="t('catalog.file_to_relation.name_for', { column: mapping.source })"
              :disable="!mapping.include"
              autocomplete="off"
              compact
            />
          </template>
        </AppPairsRow>
      </AppPairs>
      <AppTable
        v-if="selected.length && preview.length"
        :rows="tableRows"
        :columns="tableColumns"
        row-key="index"
        compact
        :paged="false"
      />
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="t('catalog.file_to_relation.create')"
        :disable="!ready"
        :loading="running"
        data-testid="load-create"
        @click="run"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.file-to-relation__tally--wrong { color: var(--dp-content-error); }
</style>
