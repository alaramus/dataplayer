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

import { filenameStem, readDelimited } from "./delimitedFile"

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
      <AppBanner v-if="schemaMode === 'new'" tone="info">
        The database may refuse this if the connection is not allowed to create schemas.
      </AppBanner>
      <div v-if="mappings.length" class="file-to-relation__mapping">
        <div
          v-for="mapping in mappings"
          :key="mapping.source"
          class="file-to-relation__column"
        >
          <AppToggle
            v-model="mapping.include"
            :label="mapping.source"
          />
          <AppInput
            v-model="mapping.target"
            label="New column"
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
  gap: 12px;
}

.file-to-relation__mapping {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 16px;
}

.file-to-relation__column {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) minmax(120px, 1fr);
  align-items: center;
  gap: 8px;
}
</style>
