<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { ConnectorsService } from "@/client"
import type { PasteColumn, PasteOffer, TablesChoice } from "@/client"
import { startedInThisTab } from "@/features/activity/transfers"
import type { ActionOutcome } from "@/features/catalog/actions"
import { forgetMoved } from "@/features/catalog/clipboard"
import CopyTablesDialog from "@/features/catalog/CopyTablesDialog.vue"
import { firstStep, offerPlace } from "@/features/catalog/pasteOffers"
import type { CrossPasteIntent, PasteStep } from "@/features/catalog/pasteOffers"
import CreateTableDialog from "@/features/grid/CreateTableDialog.vue"
import ImportDialog from "@/features/grid/ImportDialog.vue"
import { messageOf, statusOf } from "@/shared/api/errors"
import { AppButton, AppForm, AppInput, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * One Paste from another connection, from the choice to the result (D164).
 *
 * Mounted when Paste is chosen and gone when it ends. Several usable offers
 * are listed first (D166). A plain copy runs at once and shows a window only
 * for a taken name (D162); a conversion first asks what it needs: a file
 * name (D165), the columns of a new table or of the one ticked (D166), or
 * the names and links of tables copied whole (D182).
 */
const props = defineProps<{ intent: CrossPasteIntent }>()

const emit = defineEmits<{
  done: [outcome: ActionOutcome]
  /**
   * Handed to a job on the server. Not `done`: nothing has arrived to re-read
   * or announce, but what was ticked for it has been dealt with.
   */
  started: []
  sourceChanged: [connectorId: string]
  close: []
}>()

const toast = useToast()
const only = props.intent.offers.length === 1 ? props.intent.offers[0] ?? null : null
const offer = ref<PasteOffer | null>(only)
const step = ref<PasteStep | "choose">(only === null ? "choose" : firstStep(only))
const name = ref(only?.suggested_name ?? "")
const failure = ref(
  step.value === "conflict" ? only?.reason ?? "A file already exists here" : ""
)
const pending = ref(false)
const nameHint = computed(() =>
  offer.value?.name_conflict === true && name.value.trim() === offer.value.suggested_name
    ? "A file with this name is already here"
    : undefined
)

onMounted(() => {
  if (step.value === "run") void paste("refuse")
})

function choose(chosen: PasteOffer) {
  offer.value = chosen
  name.value = chosen.suggested_name ?? ""
  failure.value = chosen.name_conflict === true ? chosen.reason ?? "" : ""
  step.value = firstStep(chosen)
  if (step.value === "run") void paste("refuse")
}

async function paste(
  conflict: "refuse" | "replace" | "rename",
  columns?: PasteColumn[],
  tables?: TablesChoice,
  place?: string
) {
  const chosen = offer.value
  if (pending.value || chosen === null) return
  pending.value = true
  const intent = props.intent
  const named = chosen.workflow === "file-name" || chosen.workflow === "new-relation"
  try {
    const answer = (await ConnectorsService.paste({
      path: { connector_id: intent.destinationConnectorId },
      body: {
        source_connector_id: intent.sourceConnectorId,
        source_node_ids: intent.sourceNodeIds,
        destination_node_id: place ?? intent.destinationNodeId,
        target_node_id: intent.targetNodeId,
        mode: intent.mode,
        kind: chosen.kind,
        conflict,
        ...(named ? { name: name.value.trim() } : {}),
        ...(columns ? { columns } : {}),
        ...(tables ? { tables } : {}),
      },
    })).data
    if (answer.outcome === "started") {
      // A transfer runs on the server from here: the footer shows it, the
      // catalogs re-read as its files arrive, and this tab is told how it
      // ended (D168). A Cut is spent the moment its move starts.
      if (chosen.changes_source === true) forgetMoved(intent.sourceConnectorId, intent.sourceNodeIds)
      startedInThisTab(answer.job.id)
      emit("started")
      emit("close")
      return
    }
    if (chosen.changes_source === true) {
      forgetMoved(intent.sourceConnectorId, intent.sourceNodeIds)
      emit("sourceChanged", intent.sourceConnectorId)
    }
    emit("done", {
      done: [{ message: answer.message, reload_node_ids: answer.reload_node_ids }],
      failures: [],
      total: 1,
    })
    toast.success(answer.message)
    emit("close")
  } catch (cause) {
    const message = messageOf(cause, "Nothing was pasted")
    // A batch may have changed both ends before it failed, so the destination
    // is re-read; and what it was about stays ticked, for another try.
    if (chosen.changes_source === true) emit("sourceChanged", intent.sourceConnectorId)
    emit("done", {
      done: [{ message: "Paste ended", reload_node_ids: [intent.destinationNodeId] }],
      failures: [intent.targetNodeId, ...intent.sourceNodeIds].map((nodeId) => ({
        nodeId,
        message,
      })),
      total: 1,
    })
    // Only a file is kept or replaced; a table has no such choice.
    if (statusOf(cause) === 409 && (step.value === "run" || step.value === "file-name")) {
      step.value = "conflict"
      failure.value = message
    } else if (step.value === "run") {
      toast.error(message)
      emit("close")
    } else failure.value = message
  } finally {
    pending.value = false
  }
}

/**
 * A window reports being closed when it is taken away as well, and taking one
 * away is how this moves from one step to the next — so only the window of the
 * current step closes the paste.
 */
function closeFrom(from: PasteStep | "choose") {
  if (step.value === from) emit("close")
}

function save() {
  if (name.value.trim() && !pending.value) void paste("refuse")
}

function createTable(made: { name: string; columns: PasteColumn[] }) {
  name.value = made.name
  void paste("refuse", made.columns)
}

function addRows(pairs: { columns: PasteColumn[] }) {
  void paste("refuse", pairs.columns)
}

function copyTables(copy: { choice: TablesChoice; place: string }) {
  void paste("refuse", undefined, copy.choice, copy.place)
}
</script>

<template>
  <WindowDialog
    v-if="step === 'choose'"
    :model-value="true"
    title="Paste"
    :subtitle="`What ${intent.sourceLabel} becomes here`"
    size="compact-form"
    data-testid="cross-paste-choose"
    @update:model-value="closeFrom('choose')"
  >
    <div class="cross-paste__offers">
      <AppButton
        v-for="choice in intent.offers"
        :key="choice.kind"
        variant="secondary"
        :label="`${choice.title}: ${offerPlace(choice, intent)}`"
        :data-testid="`cross-paste-offer-${choice.kind}`"
        @click="choose(choice)"
      />
    </div>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('close')"
      />
    </template>
  </WindowDialog>
  <WindowDialog
    v-else-if="step === 'file-name' && offer"
    :model-value="true"
    :title="offer.title"
    :subtitle="`${intent.sourceLabel} into ${intent.destinationLabel}`"
    size="compact-form"
    data-testid="cross-paste-name"
    @update:model-value="closeFrom('file-name')"
  >
    <AppForm layout="section">
      <AppInput
        v-model="name"
        label="File name"
        :hint="nameHint"
        :error="failure"
        data-testid="cross-paste-file-name"
        @keyup.enter="save"
      />
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        :disable="pending"
        @click="emit('close')"
      />
      <AppButton
        label="Save"
        :disable="!name.trim()"
        :loading="pending"
        data-testid="cross-paste-save"
        @click="save"
      />
    </template>
  </WindowDialog>
  <CreateTableDialog
    v-else-if="step === 'new-relation' && offer"
    :model-value="true"
    :source-title="intent.sourceLabel"
    :source-columns="offer.source_columns ?? []"
    :fixed-destination="{
      connectorId: intent.destinationConnectorId,
      parentNodeId: intent.destinationNodeId ?? '',
      label: intent.destinationLabel,
    }"
    :running="pending"
    :error="failure"
    @update:model-value="closeFrom('new-relation')"
    @run="createTable"
  />
  <ImportDialog
    v-else-if="step === 'into-relation' && offer && intent.targetNodeId !== null"
    :model-value="true"
    :connector-id="intent.destinationConnectorId"
    :node-id="intent.targetNodeId"
    :target-columns="offer.target_columns ?? []"
    :target-label="intent.targetLabel"
    :source="{
      connectorId: intent.sourceConnectorId,
      nodeId: intent.sourceNodeIds[0] ?? '',
      label: intent.sourceLabel,
      columns: offer.source_columns ?? [],
    }"
    :running="pending"
    :error="failure"
    @update:model-value="closeFrom('into-relation')"
    @run="addRows"
  />
  <CopyTablesDialog
    v-else-if="step === 'copy-tables' && offer"
    :intent="intent"
    :running="pending"
    :error="failure"
    @close="closeFrom('copy-tables')"
    @run="copyTables"
  />
  <WindowDialog
    v-else-if="step === 'conflict' && offer"
    :model-value="true"
    title="File already exists"
    size="compact-form"
    data-testid="cross-paste-conflict"
    @update:model-value="closeFrom('conflict')"
  >
    <p>{{ failure }}. Choose what to do with the pasted {{ intent.sourceNodeIds.length > 1 ? "files" : "file" }}.</p>
    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        :disable="pending"
        @click="emit('close')"
      />
      <AppButton
        variant="secondary"
        label="Keep both"
        :loading="pending"
        data-testid="cross-paste-keep-both"
        @click="paste('rename')"
      />
      <AppButton
        v-if="offer.can_replace !== false"
        variant="danger"
        label="Replace"
        :loading="pending"
        data-testid="cross-paste-replace"
        @click="paste('replace')"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.cross-paste__offers {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}
</style>
