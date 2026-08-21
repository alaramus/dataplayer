<script setup lang="ts">
import { AxiosError } from "axios"
import { computed, ref, watch } from "vue"

import { useRunAction } from "@/features/catalog/api"
import type { ActionCommand } from "@/features/catalog/actions"
import SchemaFields from "@/shared/SchemaForm/SchemaFields.vue"
import { useSchemaForm } from "@/shared/SchemaForm/useSchemaForm"
import type { ServerError } from "@/shared/SchemaForm/useSchemaForm"

const props = defineProps<{
  command: ActionCommand | null
  connectorId: string
  nodeId: string | null
  nodeLabel: string
}>()

const emit = defineEmits<{
  "update:command": [value: ActionCommand | null]
  done: [reloadNodeId: string | null]
}>()

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

function messageOf(cause: unknown): string {
  if (cause instanceof AxiosError) {
    const detail = cause.response?.data?.detail
    if (detail && typeof detail === "object" && "message" in detail) {
      return String(detail.message)
    }
  }
  return "The action could not be performed"
}

function fieldErrorsFrom(cause: unknown): ServerError[] | null {
  if (!(cause instanceof AxiosError) || cause.response?.status !== 422) return null
  const detail = cause.response.data?.detail
  return Array.isArray(detail) ? (detail as ServerError[]) : null
}

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
    const result = await runAction.mutateAsync({
      connectorId: props.connectorId,
      name: command.name,
      nodeId: props.nodeId,
      params: { ...values.value },
      file: file.value,
    })
    emit("done", result.reload_node_id ?? null)
    close()
  } catch (cause) {
    const fieldErrors = fieldErrorsFrom(cause)
    if (fieldErrors) {
      applyServerErrors(fieldErrors)
    } else {
      failure.value = messageOf(cause)
    }
  }
}
</script>

<template>
  <q-dialog
    :model-value="open"
    @update:model-value="close"
  >
    <q-card
      v-if="command"
      style="width: 460px; max-width: 90vw"
      data-testid="action-dialog"
    >
      <q-card-section>
        <div class="text-h6">
          {{ command.label }}
        </div>
        <div class="text-caption text-grey">
          {{ nodeLabel }}
        </div>
      </q-card-section>

      <q-card-section class="q-gutter-md">
        <!-- The warning follows the declared flag, not a list of names kept
             here: an action that destroys something says so itself. -->
        <q-banner
          v-if="command.destructive"
          dense
          class="bg-orange-1"
          data-testid="action-warning"
        >
          This cannot be undone.
        </q-banner>

        <q-banner
          v-if="failure"
          dense
          class="bg-negative text-white"
          data-testid="action-error"
        >
          {{ failure }}
        </q-banner>

        <q-file
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
      </q-card-section>

      <q-card-actions align="right">
        <q-btn
          flat
          label="Cancel"
          @click="close"
        />
        <q-btn
          :color="command.destructive ? 'negative' : 'primary'"
          :label="command.label"
          :loading="runAction.isPending.value"
          data-testid="action-submit"
          @click="submit"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>
