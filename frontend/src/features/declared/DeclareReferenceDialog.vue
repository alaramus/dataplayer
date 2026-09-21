<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import type { FetchColumn } from "@/client"
import NodePicker from "@/features/catalog/NodePicker.vue"
import type { PickedNode } from "@/features/catalog/nodes"
import { useDeclareReference } from "@/features/declared/api"
import { lookupColumns } from "@/features/declared/model"
import { messageOf } from "@/shared/api/errors"
import { AppBanner, AppButton, AppForm, AppSelect } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * Draw a reference from a column here to a column anywhere else (D106).
 *
 * One window rather than the old application's two steps — mark a column,
 * walk somewhere else, mark another — whose second step lived in a store and
 * needed a badge in the toolbar to remind people it was waiting. Both ends are
 * read as one page of the node, so the columns offered are the ones the source
 * says it can look a value up in.
 */
const props = defineProps<{
  modelValue: boolean
  connectorId: string
  nodeId: string
  nodeLabel: string
}>()
const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  declared: []
}>()

const declare = useDeclareReference()
const nearColumns = ref<FetchColumn[]>([])
const nearColumn = ref("")
const far = ref<PickedNode | null>(null)
const farColumn = ref("")
const trouble = ref("")

const nearOptions = computed(() =>
  lookupColumns(nearColumns.value).map((column) => ({
    label: column.name,
    value: column.name,
  }))
)
const farOptions = computed(() =>
  lookupColumns(far.value?.columns ?? []).map((column) => ({
    label: column.name,
    value: column.name,
  }))
)
const ready = computed(
  () => nearColumn.value !== "" && farColumn.value !== "" && far.value !== null
)

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    nearColumn.value = ""
    far.value = null
    farColumn.value = ""
    trouble.value = ""
    nearColumns.value = []
    try {
      const answer = await ConnectorsService.fetchRows({
        path: { connector_id: props.connectorId },
        body: { node_id: props.nodeId, limit: 1 },
      })
      nearColumns.value = answer.data.columns
    } catch (error) {
      trouble.value = messageOf(error, "Could not read this node as rows")
    }
  },
  { immediate: true }
)

function picked(node: PickedNode | null) {
  far.value = node
  farColumn.value = ""
}

async function run() {
  const target = far.value
  if (!ready.value || target === null) return
  trouble.value = ""
  try {
    await declare.mutateAsync({
      ends: [
        {
          connector_id: props.connectorId,
          node_id: props.nodeId,
          column: nearColumn.value,
        },
        {
          connector_id: target.connectorId,
          node_id: target.node.id,
          column: farColumn.value,
        },
      ],
    })
    emit("declared")
    emit("update:modelValue", false)
  } catch (error) {
    trouble.value = messageOf(error, "Could not declare this reference")
  }
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    title="Declare a reference"
    :subtitle="`From a column of ${nodeLabel} to a column anywhere else`"
    size="form"
    sizing="stable"
    data-testid="declare-reference-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppBanner
        v-if="trouble"
        tone="error"
        data-testid="declare-reference-error"
      >
        {{ trouble }}
      </AppBanner>
      <AppSelect
        :model-value="nearColumn"
        :options="nearOptions"
        label="This column"
        data-testid="declare-reference-near-column"
        @update:model-value="nearColumn = String($event)"
      />
      <NodePicker
        :key="modelValue ? 'open' : 'closed'"
        testid="declare-reference"
        label="Points at"
        @pick="picked"
        @trouble="trouble = $event"
      />
      <AppSelect
        v-if="far !== null"
        :model-value="farColumn"
        :options="farOptions"
        label="That column"
        data-testid="declare-reference-far-column"
        @update:model-value="farColumn = String($event)"
      />
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        :disable="declare.isPending.value"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        label="Declare"
        :disable="!ready"
        :loading="declare.isPending.value"
        data-testid="declare-reference-run"
        @click="run"
      />
    </template>
  </WindowDialog>
</template>
