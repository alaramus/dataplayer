<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import type { FetchColumn, NewRelationColumn, NewRelationOptions, PasteColumn } from "@/client"
import { callsDatabases } from "@/features/catalog/nodes"
import { useAdapterTypes, useConnectors } from "@/features/connectors/api"
import { placesIn } from "@/features/grid/relationPlaces"
import type { Destination } from "@/features/grid/relationPlaces"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppBanner,
  AppButton,
  AppForm,
  AppInput,
  AppPairs,
  AppPairsRow,
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
  /**
   * Where the table goes when that is already decided — a Paste is chosen in
   * the place itself (D166) — so there is no connection or schema to pick.
   */
  fixedDestination?: { connectorId: string; parentNodeId: string; label: string } | null
  /**
   * What was chosen before, to start from: a pipeline's link keeps its
   * choices and opens this again on them (D176).
   */
  kept?: { name: string | null; columns: readonly PasteColumn[] | null } | null
  /** The button's word, where it keeps a choice rather than making the table. */
  actionLabel?: string
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
const adapterTypes = useAdapterTypes()
const connectorId = ref("")
const schemas = ref<{ label: string; value: string; kind: Destination }[]>([])
const schemaId = ref("")
const tableName = ref("")
const options = ref<NewRelationOptions | null>(null)
const mappings = ref<Mapping[]>([])
const catalogLoading = ref(false)
const optionsLoading = ref(false)
const trouble = ref("")
let catalogAsked = 0
let optionsAsked = 0

/** The source types that will take a new relation at all, by their code. */
const creating = computed(
  () =>
    new Set(
      (adapterTypes.data.value ?? [])
        .filter((type) =>
          type.capabilities.some((one) => one.code === "create_relation")
        )
        .map((type) => type.name)
    )
)

// Only connections that can take one. A source that cannot answers 501 to the
// very first question this dialog asks, and offering it would be offering a
// dead end (D45).
const targets = computed(() =>
  props.fixedDestination
    ? [{ label: props.fixedDestination.label, value: props.fixedDestination.connectorId }]
    : (connectors.data.value?.data ?? [])
    .filter(
      (connector) =>
        connector.enabled &&
        (connector.access === "structure" || connector.access === "own") &&
        creating.value.has(connector.adapter_type)
    )
    .map((connector) => ({ label: connector.name, value: connector.id }))
)
const selected = computed(() => mappings.value.filter((mapping) => mapping.include))

/** What is being made, which is what the whole form is worded around. */
const destination = computed<Destination>(
  () => schemas.value.find((place) => place.value === schemaId.value)?.kind ?? "schema"
)
// A schema the source calls a database is named so, as MySQL's are (D229).
const databases = ref(false)
const placeLabel = computed(() =>
  destination.value === "schema" && databases.value
    ? t("grid.create_table.place.database")
    : t(`grid.create_table.place.${destination.value}`)
)
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
  return title.replace(/\.[^.]+$/, "") || t("grid.create_table.default_name")
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    const initialConnector = targets.value[0]?.value ?? ""
    const reloadCurrent =
      initialConnector !== "" && connectorId.value === initialConnector
    connectorId.value = initialConnector
    tableName.value = props.kept?.name ?? defaultName(props.sourceTitle)
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
  const fixed = props.fixedDestination
  if (fixed) {
    schemas.value = [{ label: fixed.label, value: fixed.parentNodeId, kind: "schema" }]
    schemaId.value = fixed.parentNodeId
    await loadOptions(fixed.parentNodeId)
    return
  }
  catalogLoading.value = true
  trouble.value = ""
  try {
    const answer = await ConnectorsService.readCatalog({
      path: { connector_id: id },
      query: {},
    })
    if (mine !== catalogAsked) return
    databases.value = callsDatabases(answer.data)
    schemas.value = placesIn(
      answer.data,
      targets.value.find((target) => target.value === id)?.label ?? t("grid.create_table.top_level")
    )
    const first = schemas.value[0]
    schemaId.value = first?.value ?? ""
    if (first === undefined) {
      trouble.value = t("grid.create_table.nowhere")
      return
    }
    await loadOptions(schemaId.value)
  } catch (cause) {
    if (mine !== catalogAsked) return
    trouble.value = messageOf(cause, t("grid.create_table.schemas_failed"))
  } finally {
    if (mine === catalogAsked) catalogLoading.value = false
  }
}

// Immediate is important when the connector query is already warm: the open
// watcher above then chooses the first connector before this watcher exists.
// Without the immediate run, schemas appear only after changing the selection.
watch(connectorId, loadSchemas, { immediate: true })

/**
 * What the chosen place accepts, asked of the place itself.
 *
 * Called rather than watched: the first destination of a source that keeps
 * files is its top level, whose id is the empty string — the same value the
 * form was just reset to — and a watcher has nothing to observe when the
 * answer does not change.
 */
async function pickPlace(chosen: unknown) {
  const id = String(chosen ?? "")
  schemaId.value = id
  await loadOptions(id)
}

async function loadOptions(id: string) {
  const mine = (optionsAsked += 1)
  optionsLoading.value = false
  options.value = null
  mappings.value = []
  // The empty id is the top level of a source that keeps files, so it is a
  // destination like any other; only a connection with none is nothing to ask
  // about.
  if (connectorId.value === "" || schemas.value.length === 0) return
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
      trouble.value =
        answer.data.reason ?? t(`grid.create_table.cannot_accept.${destination.value}`)
      return
    }
    const choices = answer.data.column_type_options ?? []
    const initialType =
      choices.find((choice) => choice.code === "text")?.code ??
      choices[0]?.code ??
      ""
    const before = props.kept?.columns ?? null
    const known = new Set(choices.map((choice) => choice.code))
    mappings.value = props.sourceColumns.map((column) => {
      const chosen = before?.find((one) => one.source === column.name)
      return {
        source: column.name,
        target: chosen?.target ?? column.name,
        typeCode: chosen?.type_code != null && known.has(chosen.type_code) ? chosen.type_code : initialType,
        include: before === null || chosen !== undefined,
      }
    })
  } catch (cause) {
    if (mine !== optionsAsked) return
    trouble.value = messageOf(cause, t("grid.create_table.options_failed"))
  } finally {
    if (mine === optionsAsked) optionsLoading.value = false
  }
}

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
    :title="t(`grid.create_table.title.${destination}`)"
    :subtitle="
      fixedDestination
        ? t('grid.create_table.fixed_subtitle', { place: fixedDestination.label })
        : t(`grid.create_table.subtitle.${destination}`)
    "
    size="wide-form"
    sizing="stable"
    data-testid="grid-create-table-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
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
      <AppSelect
        v-if="!fixedDestination"
        v-model="connectorId"
        :options="targets"
        :label="t('grid.create_table.connection')"
        :loading="connectors.isFetching.value"
        data-testid="grid-create-table-connector"
      />
      <AppSelect
        v-if="!fixedDestination"
        :model-value="schemaId"
        :options="schemas"
        :label="placeLabel"
        :loading="loading"
        :disable="connectorId === ''"
        data-testid="grid-create-table-schema"
        @update:model-value="pickPlace"
      />
      <AppInput
        v-model="tableName"
        :label="t(`grid.create_table.name.${destination}`)"
        :hint="
          destination === 'folder'
            ? t('grid.create_table.csv_hint')
            : undefined
        "
        autocomplete="off"
        data-testid="grid-create-table-name"
      />

      <AppPairs
        v-if="mappings.length > 0"
        data-testid="grid-create-table-columns"
      >
        <template #from>
          {{ t('grid.create_table.from') }}
        </template>
        <template #to>
          {{ t(`grid.create_table.to.${destination}`) }}
        </template>
        <!-- Only where there is something to choose: every column of a
             delimited file is text, and a list of one is a control that does
             nothing but take up the line (D45). -->
        <template
          v-if="typeChoices.length > 1"
          #extra
        >
          {{ t('grid.create_table.type') }}
        </template>
        <AppPairsRow
          v-for="mapping in mappings"
          :key="mapping.source"
          :idle="!mapping.include"
          :data-testid="`grid-create-table-column-${mapping.source}`"
        >
          <template #from>
            <AppToggle
              v-model="mapping.include"
              :label="mapping.source"
            />
          </template>
          <template #to>
            <AppInput
              v-model="mapping.target"
              :aria-label="t(`grid.create_table.target_aria.${destination}`, { column: mapping.source })"
              :disable="!mapping.include"
              autocomplete="off"
              compact
            />
          </template>
          <template
            v-if="typeChoices.length > 1"
            #extra
          >
            <AppSelect
              v-model="mapping.typeCode"
              :aria-label="t('grid.create_table.type_aria', { column: mapping.source })"
              :options="typeChoices"
              :disable="!mapping.include"
              compact
            />
          </template>
        </AppPairsRow>
      </AppPairs>
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="actionLabel ?? t(`grid.create_table.run.${destination}`)"
        :disable="!ready"
        :loading="running"
        data-testid="grid-create-table-run"
        @click="run"
      />
    </template>
  </WindowDialog>
</template>
