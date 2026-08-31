<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import type { FetchColumn, NewRelationColumn, NewRelationOptions } from "@/client"
import { useConnectors } from "@/features/connectors/api"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppInput,
  AppSection,
  AppSelect,
  AppToggle,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

interface Mapping {
  source: string
  target: string
  typeCode: string
  include: boolean
}

const props = defineProps<{
  modelValue: boolean
  sourceTitle: string
  sourceColumns: FetchColumn[]
  running: boolean
  error: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  run: [value: {
    connectorId: string
    parentNodeId: string
    name: string
    columns: NewRelationColumn[]
  }]
}>()

const connectors = useConnectors()
const connectorId = ref("")
const schemas = ref<{ label: string; value: string }[]>([])
const schemaId = ref("")
const tableName = ref("")
const options = ref<NewRelationOptions | null>(null)
const mappings = ref<Mapping[]>([])
const catalogLoading = ref(false)
const optionsLoading = ref(false)
const trouble = ref("")
let catalogAsked = 0
let optionsAsked = 0

const targets = computed(() =>
  (connectors.data.value?.data ?? [])
    .filter(
      (connector) =>
        connector.enabled && (connector.access === "structure" || connector.access === "own")
    )
    .map((connector) => ({ label: connector.name, value: connector.id }))
)
const selected = computed(() => mappings.value.filter((mapping) => mapping.include))
const loading = computed(() => catalogLoading.value || optionsLoading.value)
const typeChoices = computed(() =>
  (options.value?.column_type_options ?? []).map((choice) => ({
    label: choice.title,
    value: choice.code,
  }))
)
const ready = computed(
  () =>
    options.value?.supported === true &&
    tableName.value.trim() !== "" &&
    selected.value.length > 0 &&
    selected.value.every(
      (mapping) => mapping.target.trim() !== "" && mapping.typeCode !== ""
    )
)

function defaultName(title: string): string {
  return title.replace(/\.[^.]+$/, "") || "new table"
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    const initialConnector = targets.value[0]?.value ?? ""
    const reloadCurrent =
      initialConnector !== "" && connectorId.value === initialConnector
    connectorId.value = initialConnector
    tableName.value = defaultName(props.sourceTitle)
    schemas.value = []
    schemaId.value = ""
    options.value = null
    mappings.value = []
    trouble.value = ""
    // A dialog kept mounted between openings does not change connectorId when
    // the same first destination is selected again, so its watcher has nothing
    // to observe. Re-read that destination explicitly after resetting the form.
    if (reloadCurrent) void loadSchemas(initialConnector)
  },
  { immediate: true }
)

watch(targets, (available) => {
  if (props.modelValue && connectorId.value === "") {
    connectorId.value = available[0]?.value ?? ""
  }
})

async function loadSchemas(id: string) {
  const mine = (catalogAsked += 1)
  catalogLoading.value = false
  schemas.value = []
  schemaId.value = ""
  options.value = null
  mappings.value = []
  if (id === "") return
  catalogLoading.value = true
  trouble.value = ""
  try {
    const answer = await ConnectorsService.readCatalog({
      path: { connector_id: id },
      query: {},
    })
    if (mine !== catalogAsked) return
    schemas.value = answer.data
      .filter((node) => node.kind === "schema" && node.is_system !== true)
      .map((node) => ({ label: node.name, value: node.id }))
    schemaId.value = schemas.value[0]?.value ?? ""
    if (schemaId.value === "") trouble.value = "This connection has no writable schema"
  } catch (cause) {
    if (mine !== catalogAsked) return
    trouble.value = messageOf(cause, "Could not read the destination schemas")
  } finally {
    if (mine === catalogAsked) catalogLoading.value = false
  }
}

// Immediate is important when the connector query is already warm: the open
// watcher above then chooses the first connector before this watcher exists.
// Without the immediate run, schemas appear only after changing the selection.
watch(connectorId, loadSchemas, { immediate: true })

watch(schemaId, async (id) => {
  const mine = (optionsAsked += 1)
  optionsLoading.value = false
  options.value = null
  mappings.value = []
  if (id === "" || connectorId.value === "") return
  optionsLoading.value = true
  trouble.value = ""
  try {
    const answer = await ConnectorsService.newRelationOptions({
      path: { connector_id: connectorId.value },
      body: { parent_node_id: id },
    })
    if (mine !== optionsAsked) return
    options.value = answer.data
    if (!answer.data.supported) {
      trouble.value = answer.data.reason ?? "This schema cannot accept a new table"
      return
    }
    const choices = answer.data.column_type_options ?? []
    const initialType =
      choices.find((choice) => choice.code === "text")?.code ??
      choices[0]?.code ??
      ""
    mappings.value = props.sourceColumns.map((column) => ({
      source: column.name,
      target: column.name,
      typeCode: initialType,
      include: true,
    }))
  } catch (cause) {
    if (mine !== optionsAsked) return
    trouble.value = messageOf(cause, "Could not read the table options")
  } finally {
    if (mine === optionsAsked) optionsLoading.value = false
  }
})

function run() {
  if (!ready.value) return
  emit("run", {
    connectorId: connectorId.value,
    parentNodeId: schemaId.value,
    name: tableName.value.trim(),
    columns: selected.value.map((mapping) => ({
      source: mapping.source,
      target: mapping.target.trim(),
      type_code: mapping.typeCode,
    })),
  })
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    title="Create table from this data"
    subtitle="Choose where the new table goes and which columns it receives"
    size="lg"
    data-testid="grid-create-table-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="grid-create-table-error"
      >
        {{ error }}
      </AppBanner>
      <AppBanner
        v-if="trouble"
        tone="warning"
      >
        {{ trouble }}
      </AppBanner>
      <div class="create-table__destination">
        <AppSelect
          v-model="connectorId"
          :options="targets"
          label="Connection"
          :loading="connectors.isFetching.value"
          data-testid="grid-create-table-connector"
        />
        <AppSelect
          v-model="schemaId"
          :options="schemas"
          label="Schema"
          :loading="loading"
          :disable="connectorId === ''"
          data-testid="grid-create-table-schema"
        />
        <AppInput
          v-model="tableName"
          label="Table name"
          data-testid="grid-create-table-name"
        />
      </div>

      <div
        v-if="mappings.length > 0"
        class="create-table__mapping"
      >
        <div
          v-for="mapping in mappings"
          :key="mapping.source"
          class="create-table__column"
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
          <AppSelect
            v-model="mapping.typeCode"
            label="Type"
            :options="typeChoices"
            :disable="!mapping.include"
            compact
          />
        </div>
      </div>
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
        data-testid="grid-create-table-run"
        @click="run"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.create-table__destination {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}

.create-table__mapping {
  display: grid;
  gap: 8px;
}

.create-table__column {
  display: grid;
  grid-template-columns:
    minmax(140px, 1fr)
    minmax(140px, 1fr)
    minmax(120px, 0.8fr);
  align-items: center;
  gap: 8px;
}
</style>
