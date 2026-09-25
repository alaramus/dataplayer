<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { ConnectorsService } from "@/client"
import type { ActionOutcome } from "@/features/catalog/actions"
import { forgetMoved } from "@/features/catalog/clipboard"
import { firstStep } from "@/features/catalog/pasteOffers"
import type { CrossPasteIntent } from "@/features/catalog/pasteOffers"
import { messageOf, statusOf } from "@/shared/api/errors"
import { AppButton, AppForm, AppInput, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * One Paste from another connection, from the choice to the result (D164).
 *
 * Mounted when Paste is chosen and gone when it ends. A plain copy runs at
 * once and shows a window only for a taken name (D162); a conversion first
 * asks for the name of what it makes (D165).
 */
const props = defineProps<{ intent: CrossPasteIntent }>()

const emit = defineEmits<{
  done: [outcome: ActionOutcome]
  sourceChanged: [connectorId: string]
  close: []
}>()

const toast = useToast()
const offer = computed(() => props.intent.offer)
const step = ref(firstStep(props.intent.offer))
const name = ref(props.intent.offer.suggested_name ?? "")
const failure = ref(
  step.value === "conflict" ? props.intent.offer.reason ?? "A file already exists here" : ""
)
const pending = ref(false)
const nameHint = computed(() =>
  offer.value.name_conflict === true && name.value.trim() === offer.value.suggested_name
    ? "A file with this name is already here"
    : undefined
)

onMounted(() => {
  if (step.value === "run") void paste("refuse")
})

async function paste(conflict: "refuse" | "replace" | "rename") {
  if (pending.value) return
  pending.value = true
  const intent = props.intent
  try {
    const result = (await ConnectorsService.paste({
      path: { connector_id: intent.destinationConnectorId },
      body: {
        source_connector_id: intent.sourceConnectorId,
        source_node_ids: intent.sourceNodeIds,
        destination_node_id: intent.destinationNodeId,
        mode: intent.mode,
        kind: intent.offer.kind,
        conflict,
        ...(intent.offer.suggested_name != null ? { name: name.value.trim() } : {}),
      },
    })).data
    if (intent.offer.changes_source === true) {
      forgetMoved(intent.sourceConnectorId, intent.sourceNodeIds)
      emit("sourceChanged", intent.sourceConnectorId)
    }
    emit("done", {
      done: [{ message: result.message, reload_node_ids: result.reload_node_ids }],
      failures: [],
      total: 1,
    })
    toast.success(result.message)
    emit("close")
  } catch (cause) {
    // A batch may have changed both ends before it failed.
    if (intent.offer.changes_source === true) emit("sourceChanged", intent.sourceConnectorId)
    emit("done", {
      done: [{ message: "Paste ended", reload_node_ids: [intent.destinationNodeId] }],
      failures: [],
      total: 1,
    })
    const message = messageOf(cause, "Nothing was pasted")
    if (statusOf(cause) === 409) {
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

function save() {
  if (name.value.trim() && !pending.value) void paste("refuse")
}
</script>

<template>
  <WindowDialog
    v-if="step === 'name'"
    :model-value="true"
    :title="offer.title"
    :subtitle="`${intent.sourceLabel} into ${intent.destinationLabel}`"
    size="compact-form"
    data-testid="cross-paste-name"
    @update:model-value="emit('close')"
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
  <WindowDialog
    v-else-if="step === 'conflict'"
    :model-value="true"
    title="File already exists"
    size="compact-form"
    data-testid="cross-paste-conflict"
    @update:model-value="emit('close')"
  >
    <p>{{ failure }}. Choose what to do with the pasted file.</p>
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
