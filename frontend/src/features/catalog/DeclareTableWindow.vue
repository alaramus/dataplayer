<script setup lang="ts">
import { useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, ref, watch } from "vue"

import { ConnectorsService } from "@/client"
import type { TableChanged } from "@/client"
import type { ActionOutcome } from "@/features/catalog/actions"
import {
  declarationOf,
  draftOf,
  draftProblem,
  foundText,
  TYPE_OPTIONS,
  withField,
} from "@/features/catalog/declaredTable"
import type { TableDraft } from "@/features/catalog/declaredTable"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppForm,
  AppInput,
  AppPairs,
  AppPairsRow,
  AppSelect,
  AppSpinner,
  AppToggle,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * "Describe as table" on a folder, or on the table already declared over one
 * (D170). The server proposes the fields of the folder's first hashes; the
 * ticked ones, in this order, are the columns after `key`. Nothing here is
 * written into the source, and Remove table touches no key.
 */
const props = defineProps<{
  connectorId: string
  nodeId: string
  nodeLabel: string
}>()

const emit = defineEmits<{
  done: [outcome: ActionOutcome]
  close: []
}>()

const toast = useToast()
const queryClient = useQueryClient()

const proposal = useQuery({
  queryKey: ["table-proposal", props.connectorId, props.nodeId],
  queryFn: async () =>
    (await ConnectorsService.tableProposal({
      path: { connector_id: props.connectorId },
      body: { node_id: props.nodeId },
    })).data,
  retry: false,
  gcTime: 0,
})

const draft = ref<TableDraft | null>(null)
watch(
  () => proposal.data.value,
  (value) => {
    if (value !== undefined && draft.value === null) draft.value = draftOf(value)
  },
  { immediate: true }
)

const adding = ref("")
const addError = ref("")
const failure = ref("")
const pending = ref<"save" | "remove" | null>(null)

const problem = computed(() => (draft.value === null ? null : draftProblem(draft.value)))

function add() {
  if (draft.value === null) return
  const next = withField(draft.value, adding.value)
  if (typeof next === "string") {
    addError.value = next
    return
  }
  draft.value = next
  adding.value = ""
  addError.value = ""
}

async function save() {
  if (draft.value === null || problem.value !== null || pending.value !== null) return
  pending.value = "save"
  failure.value = ""
  try {
    finish((await ConnectorsService.declareTable({
      path: { connector_id: props.connectorId },
      body: declarationOf(props.nodeId, draft.value),
    })).data)
  } catch (cause) {
    failure.value = messageOf(cause, "The table could not be saved")
  } finally {
    pending.value = null
  }
}

async function remove() {
  if (pending.value !== null) return
  pending.value = "remove"
  failure.value = ""
  try {
    finish((await ConnectorsService.removeTable({
      path: { connector_id: props.connectorId },
      query: { node_id: props.nodeId },
    })).data)
  } catch (cause) {
    failure.value = messageOf(cause, "The table could not be removed")
  } finally {
    pending.value = null
  }
}

/**
 * Everything read of this connection's catalog is from before: the table
 * stands beside its folder now, or no longer does, and its rows and model have
 * other columns.
 */
function finish(changed: TableChanged) {
  queryClient.removeQueries({ queryKey: ["catalog", props.connectorId] })
  queryClient.removeQueries({ queryKey: ["nodePath", props.connectorId] })
  void queryClient.invalidateQueries({ queryKey: ["table-offer", props.connectorId] })
  void queryClient.invalidateQueries({ queryKey: ["rows", props.connectorId] })
  void queryClient.invalidateQueries({ queryKey: ["relationModel", props.connectorId] })
  toast.success(changed.message)
  emit("done", {
    done: [{ message: changed.message, reload_node_ids: changed.reload_node_ids }],
    failures: [],
    total: 1,
  })
  emit("close")
}
</script>

<template>
  <WindowDialog
    :model-value="true"
    title="Describe as table"
    :subtitle="`The hashes in ${nodeLabel}, one row each`"
    size="medium-form"
    sizing="stable"
    data-testid="declare-table"
    @update:model-value="emit('close')"
  >
    <AppSpinner v-if="proposal.isPending.value" />
    <AppBanner
      v-else-if="proposal.isError.value"
      tone="error"
    >
      {{ messageOf(proposal.error.value, "The folder could not be read") }}
    </AppBanner>
    <AppForm
      v-else-if="draft"
      layout="section"
    >
      <AppBanner
        v-if="failure"
        tone="error"
        data-testid="declare-table-error"
      >
        {{ failure }}
      </AppBanner>
      <AppInput
        v-model="draft.name"
        label="Table name"
        autocomplete="off"
        data-testid="declare-table-name"
      />
      <AppBanner
        v-if="draft.fields.length === 0"
        tone="info"
      >
        No hash in this folder holds a field yet. Add the fields its keys will have.
      </AppBanner>
      <AppPairs
        v-else
        data-testid="declare-table-fields"
      >
        <template #from>
          Field
        </template>
        <template #to>
          Column type
        </template>
        <template #extra>
          Found in
        </template>
        <template #aside>
          {{ draft.sampled }} sampled
        </template>
        <AppPairsRow
          v-for="field in draft.fields"
          :key="field.name"
          :idle="!field.ticked"
          :data-testid="`declare-table-field-${field.name}`"
        >
          <template #from>
            <AppToggle
              v-model="field.ticked"
              :label="field.name"
            />
          </template>
          <template #to>
            <AppSelect
              v-model="field.type"
              :aria-label="`Type of ${field.name}`"
              :options="TYPE_OPTIONS"
              :disable="!field.ticked"
              compact
            />
          </template>
          <template #extra>
            <span class="declare-table__found">{{ foundText(field, draft.sampled) }}</span>
          </template>
        </AppPairsRow>
      </AppPairs>
      <div class="declare-table__add">
        <AppInput
          v-model="adding"
          label="Add a field"
          :error="addError"
          autocomplete="off"
          data-testid="declare-table-add-name"
          @keyup.enter="add"
        />
        <AppButton
          variant="secondary"
          label="Add"
          :disable="!adding.trim()"
          data-testid="declare-table-add"
          @click="add"
        />
      </div>
    </AppForm>
    <template #actions>
      <!-- Why Save is off, at the foot beside it (D187), where Add widgets
           says what it is waiting for: under the fields it read as help. -->
      <span
        v-if="problem"
        class="declare-table__problem"
        data-testid="declare-table-problem"
      >{{ problem }}</span>
      <AppButton
        v-if="draft?.declared"
        variant="danger"
        label="Remove table"
        :loading="pending === 'remove'"
        :disable="pending === 'save'"
        data-testid="declare-table-remove"
        @click="remove"
      />
      <AppButton
        variant="quiet"
        label="Cancel"
        :disable="pending !== null"
        @click="emit('close')"
      />
      <AppButton
        label="Save"
        :disable="draft === null || problem !== null || pending === 'remove'"
        :loading="pending === 'save'"
        data-testid="declare-table-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.declare-table__add {
  display: flex;
  align-items: flex-start;
  gap: var(--dp-space-2);
}
.declare-table__add > :first-child {
  flex: 1;
}
.declare-table__problem {
  margin-right: auto;
  padding-left: var(--dp-space-2);
  color: var(--dp-text-muted);
}
.declare-table__found {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
</style>
