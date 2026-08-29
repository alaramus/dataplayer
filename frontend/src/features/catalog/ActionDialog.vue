<script setup lang="ts">
import { computed, ref, watch } from "vue"

import { useRunAction } from "@/features/catalog/api"
import { summarize } from "@/features/catalog/actions"
import type { ActionCommand, ActionOutcome } from "@/features/catalog/actions"
import { fieldErrorsFrom, messageOf } from "@/shared/api/errors"
import SchemaFields from "@/shared/SchemaForm/SchemaFields.vue"
import { useSchemaForm } from "@/shared/SchemaForm/useSchemaForm"
import {
  AppBanner,
  AppButton,
  AppFileInput,
  AppSection,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  command: ActionCommand | null
  connectorId: string
  /** Everything the filled form is applied to, one node at a time. */
  nodeIds: (string | null)[]
  nodeLabel: string
}>()

const emit = defineEmits<{
  "update:command": [value: ActionCommand | null]
  done: [outcome: ActionOutcome]
}>()

const toast = useToast()
const runAction = useRunAction()
const { values, errors, reset, applyServerErrors } = useSchemaForm()

const file = ref<File | null>(null)
const failure = ref("")

const open = computed(() => props.command !== null)

watch(
  () => props.command,
  (command) => {
    failure.value = ""
    file.value = null
    reset(command?.fields ?? [])
  }
)

function close() {
  emit("update:command", null)
}

async function submit() {
  const command = props.command
  if (!command) return
  if (command.takesFile && !file.value) {
    failure.value = "Choose a file first"
    return
  }

  failure.value = ""
  try {
    const outcome = await runAction.mutateAsync({
      connectorId: props.connectorId,
      name: command.name,
      nodeIds: props.nodeIds,
      params: { ...values.value },
      file: file.value,
    })
    // One line whatever the size of the set: what was done, and what was
    // refused by whom. A refusal in the middle does not stop the rest.
    const said = summarize(outcome, command.label)
    if (outcome.failures.length > 0) toast.error(said)
    else toast.success(said)
    emit("done", outcome)
    close()
  } catch (cause) {
    const fieldErrors = fieldErrorsFrom(cause)
    if (fieldErrors) {
      applyServerErrors(fieldErrors)
    } else {
      failure.value = messageOf(cause, "The action could not be performed")
    }
  }
}
</script>

<template>
  <WindowDialog
    v-if="command"
    :model-value="open"
    size="sm"
    :title="command.label"
    :subtitle="nodeLabel"
    data-testid="action-dialog"
    @update:model-value="close"
  >
    <AppSection gutter>
      <!-- The warning follows the declared flag, not a list of names kept
           here: an action that destroys something says so itself. -->
      <AppBanner
        v-if="command.destructive"
        tone="warning"
        data-testid="action-warning"
      >
        This cannot be undone.
      </AppBanner>

      <AppBanner
        v-if="failure"
        tone="error"
        data-testid="action-error"
      >
        {{ failure }}
      </AppBanner>

      <AppFileInput
        v-if="command.takesFile"
        v-model="file"
        label="File"
        data-testid="action-file"
      />

      <SchemaFields
        v-if="command.fields.length"
        v-model="values"
        :fields="command.fields"
        :errors="errors"
      />
    </AppSection>

    <template #actions>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="close"
      />
      <AppButton
        :variant="command.destructive ? 'danger' : 'primary'"
        :label="command.label"
        :loading="runAction.isPending.value"
        data-testid="action-submit"
        @click="submit"
      />
    </template>
  </WindowDialog>
</template>
