<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ConnectionCheckResult, ConnectorPublic } from "@/client"
import ConnectionCheck from "@/features/connectors/ConnectionCheck.vue"
import { fieldErrorsFrom } from "@/shared/api/errors"
import SchemaFields from "@/shared/SchemaForm/SchemaFields.vue"
import { jsonSchemaToZod, schemaToFields } from "@/shared/SchemaForm/jsonSchema"
import type { JsonSchema } from "@/shared/SchemaForm/jsonSchema"
import { useSchemaForm } from "@/shared/SchemaForm/useSchemaForm"
import {
  AppButton,
  AppDialog,
  AppInput,
  AppSection,
  AppSelect,
  useConfirm,
  useToast,
} from "@/shared/ui"
import {
  useAdapterTypes,
  useCheckDraft,
  useCreateConnector,
  useDeleteConnector,
  useUpdateConnector,
} from "@/features/connectors/api"
import { useConnectorChecksStore } from "@/stores/connectorChecks"

const props = defineProps<{
  modelValue: boolean
  connector: ConnectorPublic | null
}>()

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()

const toast = useToast()
const confirm = useConfirm()
const checks = useConnectorChecksStore()
const adapterTypes = useAdapterTypes()
const createConnector = useCreateConnector()
const updateConnector = useUpdateConnector()
const removeConnector = useDeleteConnector()
const checkDraft = useCheckDraft()

// The composable is destructured into individual refs: templates unwrap only
// top-level refs, otherwise every use would read form.values.value.
const {
  values: optionValues,
  errors: optionErrors,
  reset: resetOptions,
  validate: validateOptions,
  applyServerErrors,
} = useSchemaForm()

const name = ref("")
const nameError = ref("")
const adapterType = ref<string | null>(null)
const checkResult = ref<ConnectionCheckResult | null>(null)

const isEdit = computed(() => props.connector !== null)

const typeOptions = computed(() =>
  (adapterTypes.data.value ?? []).map((type) => ({ label: type.title, value: type.name }))
)

const selectedSchema = computed<JsonSchema | null>(() => {
  const type = (adapterTypes.data.value ?? []).find((item) => item.name === adapterType.value)
  return type ? (type.options_schema as unknown as JsonSchema) : null
})

const fields = computed(() => (selectedSchema.value ? schemaToFields(selectedSchema.value) : []))

// While editing, secret fields arrive empty: the server never returns them.
const secretPlaceholder = computed(() => (isEdit.value ? "Leave unchanged" : undefined))

const saving = computed(() => createConnector.isPending.value || updateConnector.isPending.value)

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    checkResult.value = null
    nameError.value = ""
    if (props.connector) {
      name.value = props.connector.name
      adapterType.value = props.connector.adapter_type
      resetOptions(fields.value, props.connector.config as Record<string, unknown>)
    } else {
      name.value = ""
      adapterType.value = null
      resetOptions([])
    }
  }
)

watch(adapterType, () => {
  checkResult.value = null
  if (props.connector && adapterType.value === props.connector.adapter_type) {
    resetOptions(fields.value, props.connector.config as Record<string, unknown>)
  } else {
    resetOptions(fields.value)
  }
})

function filledOptions(): Record<string, unknown> {
  // Empty secret fields are not sent: the server keeps the stored values.
  const result: Record<string, unknown> = {}
  for (const field of fields.value) {
    const value = optionValues.value[field.name]
    if (field.kind === "password" && (value === "" || value === null)) continue
    result[field.name] = value
  }
  return result
}

function validateName(): boolean {
  nameError.value = name.value.trim() === "" ? "Name is required" : ""
  return nameError.value === ""
}

async function check() {
  if (!adapterType.value) return
  checkResult.value = null
  try {
    checkResult.value = await checkDraft.mutateAsync({
      adapter_type: adapterType.value,
      options: filledOptions(),
      connector_id: props.connector?.id ?? null,
    })
    // The dot beside the connection is what a user reads afterwards, and this
    // is the only check there is: the same values, exercised the same way.
    if (props.connector) checks.record(props.connector.id, checkResult.value.ok)
  } catch (error) {
    const serverErrors = fieldErrorsFrom(error)
    if (serverErrors) {
      applyServerErrors(serverErrors)
    } else {
      toast.error("Could not run the check")
    }
  }
}

async function remove() {
  const connector = props.connector
  if (!connector) return

  const answer = await confirm({
    title: "Delete connection",
    message: `The connection "${connector.name}" will be deleted permanently.`,
    confirmLabel: "Delete",
    danger: true,
  })
  if (!answer) return

  await removeConnector.mutateAsync(connector.id)
  // The dot outlives the row otherwise: an id can be reused by nothing, but a
  // record nobody prunes is a record that grows for as long as the page lives.
  checks.forget(connector.id)
  toast.success("Connection deleted")
  emit("update:modelValue", false)
}

async function submit() {
  if (!adapterType.value || !selectedSchema.value) return
  const nameValid = validateName()
  // While editing an empty password is allowed, so the schema is only enforced
  // for a new connection.
  const valuesValid = isEdit.value ? true : validateOptions(jsonSchemaToZod(selectedSchema.value))
  if (!nameValid || !valuesValid) return

  try {
    if (props.connector) {
      await updateConnector.mutateAsync({
        connectorId: props.connector.id,
        body: { name: name.value, options: filledOptions() },
      })
    } else {
      await createConnector.mutateAsync({
        name: name.value,
        adapter_type: adapterType.value,
        options: filledOptions(),
      })
    }
    toast.success("Connection saved")
    emit("update:modelValue", false)
  } catch (error) {
    const serverErrors = fieldErrorsFrom(error)
    if (serverErrors) {
      applyServerErrors(serverErrors)
    } else {
      toast.error("Could not save the connection")
    }
  }
}
</script>

<template>
  <AppDialog
    :model-value="modelValue"
    size="md"
    :title="isEdit ? 'Edit connection' : 'New connection'"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppInput
        v-model="name"
        label="Name"
        data-testid="connector-name"
        :error="nameError"
      />

      <AppSelect
        v-model="adapterType"
        :options="typeOptions"
        label="Source type"
        data-testid="connector-type"
        :disable="isEdit"
        :loading="adapterTypes.isLoading.value"
      />

      <SchemaFields
        v-if="fields.length"
        v-model="optionValues"
        :fields="fields"
        :errors="optionErrors"
        :secret-placeholder="secretPlaceholder"
      />

      <ConnectionCheck :result="checkResult" />
    </AppSection>

    <template #actions>
      <!-- Deleting lives here rather than in the list: this window is where a
           connection is shown, and one home for a command cannot drift from
           another. It stands apart from the rest, on the left. -->
      <AppButton
        v-if="isEdit"
        variant="danger-quiet"
        label="Delete"
        data-testid="delete-connector"
        :loading="removeConnector.isPending.value"
        @click="remove"
      />
      <q-space />
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        variant="secondary"
        label="Check"
        data-testid="check-draft"
        :disable="!adapterType"
        :loading="checkDraft.isPending.value"
        @click="check"
      />
      <AppButton
        label="Save"
        data-testid="save-connector"
        :disable="!adapterType"
        :loading="saving"
        @click="submit"
      />
    </template>
  </AppDialog>
</template>
