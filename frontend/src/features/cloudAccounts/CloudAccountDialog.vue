<script setup lang="ts">
import { AxiosError } from "axios"
import { computed, ref, watch } from "vue"

import type { CloudAccountPublic } from "@/client"
import { accountFields, settingsFor } from "@/features/cloudAccounts/accounts"
import {
  useCloudAccountSchema,
  useCreateCloudAccount,
  useUpdateCloudAccount,
} from "@/features/cloudAccounts/api"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import SchemaFields from "@/shared/SchemaForm/SchemaFields.vue"
import type { JsonSchema } from "@/shared/SchemaForm/jsonSchema"
import { useSchemaForm } from "@/shared/SchemaForm/useSchemaForm"
import type { ServerError } from "@/shared/SchemaForm/useSchemaForm"
import { AppBanner, AppButton, AppForm, AppInput, AppSelect, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * Making a cloud account, or changing one (D451).
 *
 * The fields are the server's, one schema per kind, drawn by the form that
 * draws a connection's: which methods there are, and which sign in as this
 * server (D452), is decided there. An edit keeps its kind and shows its
 * stored secrets as stored; a secret left alone is kept.
 */
const props = defineProps<{
  modelValue: boolean
  /** The account being changed; null makes a new one. */
  account?: CloudAccountPublic | null
  /** The kinds a new account may be, when a connection's field asked for one. */
  kinds?: string[] | null
}>()
const emit = defineEmits<{
  "update:modelValue": [open: boolean]
  /** The id of the account just made, so a form can point at it. */
  created: [id: string]
}>()

const toast = useToast()
const schemas = useCloudAccountSchema(computed(() => props.modelValue))
const create = useCreateCloudAccount()
const update = useUpdateCloudAccount()
const form = useSchemaForm()

const name = ref("")
const chosenKind = ref("aws")
const error = ref("")

const editing = computed(() => props.account ?? null)
const kindSchemas = computed(() => schemas.data.value?.kinds ?? [])
const kindOptions = computed(() =>
  kindSchemas.value
    .filter((one) => !props.kinds?.length || props.kinds.includes(one.kind))
    .map((one) => ({ label: one.title, value: one.kind }))
)
const schema = computed<JsonSchema | null>(
  () => (kindSchemas.value.find((one) => one.kind === chosenKind.value)?.json_schema as JsonSchema | undefined) ?? null
)
const fields = computed(() =>
  schema.value === null ? [] : accountFields(schema.value, form.values.value.method)
)
const busy = computed(() => create.isPending.value || update.isPending.value)

function start() {
  const account = editing.value
  name.value = account?.name ?? ""
  chosenKind.value = account?.kind ?? props.kinds?.[0] ?? "aws"
  error.value = ""
  form.reset(fields.value, account ? { ...account.settings, method: account.method } : {})
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) start()
  },
  { immediate: true }
)
// A kind or a method chosen anew draws its own fields; what was typed in the
// ones they share stays.
watch(
  [schema, () => form.values.value.method],
  () => {
    if (props.modelValue) form.reset(fields.value, form.values.value)
  }
)
watch(chosenKind, () => {
  if (props.modelValue && !editing.value) form.reset(fields.value, {})
})

async function save() {
  if (busy.value || name.value.trim() === "") return
  error.value = ""
  const settings = settingsFor(fields.value, form.values.value)
  try {
    if (editing.value) {
      await update.mutateAsync({ id: editing.value.id, body: { name: name.value.trim(), settings } })
      toast.success(t("cloud_accounts.dialog.saved"))
    } else {
      const made = await create.mutateAsync({ name: name.value.trim(), settings })
      toast.success(t("cloud_accounts.dialog.made"))
      emit("created", made.id)
    }
    emit("update:modelValue", false)
  } catch (cause) {
    const detail: unknown = cause instanceof AxiosError ? cause.response?.data?.detail : undefined
    if (Array.isArray(detail)) {
      form.applyServerErrors(detail as ServerError[])
      return
    }
    error.value = messageOf(cause, t("cloud_accounts.dialog.save_failed"))
  }
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    :title="editing ? t('cloud_accounts.dialog.title_edit') : t('cloud_accounts.dialog.title_new')"
    :subtitle="t('cloud_accounts.dialog.subtitle')"
    size="form"
    sizing="stable"
    data-testid="cloud-account-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppForm layout="section">
      <AppBanner
        v-if="error"
        tone="error"
      >
        {{ error }}
      </AppBanner>
      <AppInput
        v-model="name"
        :label="t('cloud_accounts.dialog.name')"
        autofocus
        data-testid="cloud-account-name"
      />
      <AppSelect
        :model-value="chosenKind"
        :options="kindOptions"
        :label="t('cloud_accounts.dialog.kind')"
        :disable="editing !== null || kindOptions.length < 2"
        data-testid="cloud-account-kind"
        @update:model-value="chosenKind = String($event)"
      />
      <SchemaFields
        v-model="form.values.value"
        :fields="fields"
        :errors="form.errors.value"
        :secrets-are-stored="editing !== null"
      />
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        @click="emit('update:modelValue', false)"
      />
      <AppButton
        :label="editing ? t('cloud_accounts.dialog.save') : t('cloud_accounts.dialog.make')"
        :disable="name.trim() === ''"
        :loading="busy"
        data-testid="cloud-account-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>
