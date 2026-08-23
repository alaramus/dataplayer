<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ConnectionCheckResult, ConnectorPublic } from "@/client"
import ConnectionCheck from "@/features/connectors/ConnectionCheck.vue"
import { fieldErrorsFrom } from "@/shared/api/errors"
import SchemaFields from "@/shared/SchemaForm/SchemaFields.vue"
import { jsonSchemaToZod, schemaToFields } from "@/shared/SchemaForm/jsonSchema"
import type { JsonSchema } from "@/shared/SchemaForm/jsonSchema"
import { useSchemaForm } from "@/shared/SchemaForm/useSchemaForm"
import { adapterIcon } from "@/features/connectors/adapters"
import { AppButton, AppDialog, AppInput, AppSection, useConfirm, useToast } from "@/shared/ui"
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
  /** The type picked in the catalog; null while editing, where it is read off
      the connector instead. */
  adapterType?: string | null
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  /** Only ever heard when this window was reached from the catalog. */
  back: []
}>()

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
// Named apart from the `adapterType` prop: the prop is what the catalog
// chose, this is what the window is working on.
const chosenType = ref<string | null>(null)
const checkResult = ref<ConnectionCheckResult | null>(null)

const isEdit = computed(() => props.connector !== null)

const selectedType = computed(
  () => (adapterTypes.data.value ?? []).find((item) => item.name === chosenType.value) ?? null
)

const selectedSchema = computed<JsonSchema | null>(
  () => (selectedType.value?.options_schema as unknown as JsonSchema | undefined) ?? null
)

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
      chosenType.value = props.connector.adapter_type
      resetOptions(fields.value, props.connector.config as Record<string, unknown>)
    } else {
      name.value = ""
      // Decided in the catalog, which is the only way to reach this window
      // for a new connection.
      chosenType.value = props.adapterType ?? null
      // Read after the type is set, and not left to the watcher below: coming
      // back to the same type twice does not change the ref, so the watcher
      // would not fire and the previous answers would still be in the form.
      resetOptions(fields.value)
    }
  }
)

watch(chosenType, () => {
  checkResult.value = null
  if (props.connector && chosenType.value === props.connector.adapter_type) {
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
  if (!chosenType.value) return
  checkResult.value = null
  try {
    checkResult.value = await checkDraft.mutateAsync({
      adapter_type: chosenType.value,
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
  if (!chosenType.value || !selectedSchema.value) return
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
        adapter_type: chosenType.value,
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

      <!-- What the type is, not a choice of it: it was made in the catalog,
           and it never changes afterwards. A disabled dropdown would leave a
           control on screen that does nothing. -->
      <div
        v-if="selectedType"
        class="connector-dialog__type"
        data-testid="connector-type"
      >
        <q-icon
          :name="adapterIcon(selectedType.name)"
          size="24px"
        />
        <div class="connector-dialog__type-text">
          <span>{{ selectedType.title }}</span>
          <span class="connector-dialog__type-category">{{ selectedType.category_title }}</span>
        </div>
      </div>

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
      <!-- Only when this window was reached from the catalog: while editing
           there is nothing behind it to go back to. -->
      <AppButton
        v-if="!isEdit"
        variant="quiet"
        label="Back"
        data-testid="back-to-catalog"
        @click="emit('back')"
      />
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        variant="secondary"
        label="Check"
        data-testid="check-draft"
        :disable="!chosenType"
        :loading="checkDraft.isPending.value"
        @click="check"
      />
      <AppButton
        label="Save"
        data-testid="save-connector"
        :disable="!chosenType"
        :loading="saving"
        @click="submit"
      />
    </template>
  </AppDialog>
</template>

<style scoped>
.connector-dialog__type {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.connector-dialog__type-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.connector-dialog__type-category {
  font-size: 12px;
  opacity: 0.6;
}
</style>
