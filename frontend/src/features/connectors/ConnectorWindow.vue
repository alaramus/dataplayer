<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ConnectionCheckResult, ConnectorPublic } from "@/client"
import ConnectionCheck from "@/features/connectors/ConnectionCheck.vue"
import { adapterIcon } from "@/features/connectors/adapters"
import {
  useAdapterTypes,
  useCheckDraft,
  useCreateConnector,
  useDeleteConnector,
  useDescribeDraft,
  useParseUrl,
  useUpdateConnector,
} from "@/features/connectors/api"
import { fieldErrorsFrom, messageOf } from "@/shared/api/errors"
import SchemaFields from "@/shared/SchemaForm/SchemaFields.vue"
import { fieldGroups, fieldsToZod, readSchema } from "@/shared/SchemaForm/jsonSchema"
import type { FieldSpec, JsonSchema } from "@/shared/SchemaForm/jsonSchema"
import { useSchemaForm } from "@/shared/SchemaForm/useSchemaForm"
import {
  AppButton,
  AppIconButton,
  AppInput,
  AppSpinner,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { useConnectorChecksStore } from "@/stores/connectorChecks"

/**
 * One connection, in a window of its own.
 *
 * Laid out after the reference: the name on top, the fields in tabs the
 * server named, an address on one line because the options model says host
 * and port are one, the connection string underneath, and Test Connection
 * beside what the last check said. See the spec, O6 to O9.
 *
 * Several of these are open at once, so nothing here may assume it is the
 * only one: everything it reads it reads through vue-query, and everything it
 * changes it reports upwards.
 */
const props = defineProps<{
  /** The stored connection, or null for one being created. */
  connector: ConnectorPublic | null
  /** The type chosen in the catalog; used only while creating. */
  adapterType: string | null
}>()

const emit = defineEmits<{
  /** Saved a new connection: the window becomes that connection's window. */
  created: [connector: ConnectorPublic]
  close: []
  /** Close this window and go back to the catalog. New connections only:
      the type of a stored one is settled, so there is nothing behind it. */
  back: []
  /** Whether there is anything worth asking about before closing. */
  "update:dirty": [value: boolean]
}>()

const toast = useToast()
const confirm = useConfirm()
const checks = useConnectorChecksStore()
const adapterTypes = useAdapterTypes()
const createConnector = useCreateConnector()
const updateConnector = useUpdateConnector()
const removeConnector = useDeleteConnector()
const checkDraft = useCheckDraft()
const describeDraft = useDescribeDraft()
const parseUrl = useParseUrl()

const {
  values: optionValues,
  errors: optionErrors,
  reset: resetOptions,
  validate: validateOptions,
  applyServerErrors,
} = useSchemaForm()

const name = ref("")
const nameError = ref("")
const checkResult = ref<ConnectionCheckResult | null>(null)
const connectionString = ref("")
// Null while the source has never been asked; false once it has answered 501.
const hasConnectionString = ref<boolean | null>(null)
const dirty = ref(false)

// The saved connection this window is on. Held here rather than read off the
// prop so that Apply on a new connection turns this into an edit window
// without the parent having to re-create the component. See O7.
const saved = ref<ConnectorPublic | null>(null)

const isEdit = computed(() => saved.value !== null)
const typeName = computed(() => saved.value?.adapter_type ?? props.adapterType ?? null)

const selectedType = computed(
  () => (adapterTypes.data.value ?? []).find((item) => item.name === typeName.value) ?? null
)

const selectedSchema = computed<JsonSchema | null>(
  () => (selectedType.value?.options_schema as unknown as JsonSchema | undefined) ?? null
)

// What the schema turns out to be: a plain list of fields, or a choice of
// ways to connect with the fields that follow from it. The screen never
// branches on the source type — only on the shape of what it was sent.
const shape = computed(() => (selectedSchema.value ? readSchema(selectedSchema.value) : null))

/** The code of the chosen variant, or null when there is nothing to choose. */
const variantTag = computed(() => {
  const current = shape.value
  if (current?.kind !== "variants") return null
  const chosen = optionValues.value[current.discriminator.name]
  return typeof chosen === "string" ? chosen : String(current.discriminator.defaultValue)
})

/**
 * The fields on screen: what every way of connecting has, then the choice
 * itself, then what this one adds.
 *
 * The choice sits below the common fields rather than between the port and
 * the user, as the reference tool has it, because a field declares a tab and
 * a row but no ordinal — and one line is not worth a third coordinate.
 */
const activeFields = computed<FieldSpec[]>(() => {
  const current = shape.value
  if (!current) return []
  if (current.kind === "plain") return current.fields
  const tag = variantTag.value ?? ""
  return [...current.common, current.discriminator, ...(current.byVariant[tag] ?? [])]
})

/**
 * Every field the schema can produce, whichever variant is chosen.
 *
 * What the form is initialised from: a value typed before the method was
 * switched is then still there on switching back, and only `activeFields`
 * decides what is drawn and what is sent.
 */
const allFields = computed<FieldSpec[]>(() => {
  const current = shape.value
  if (!current) return []
  if (current.kind === "plain") return current.fields
  const collected = [
    ...current.common,
    current.discriminator,
    ...Object.values(current.byVariant).flat(),
  ]
  return collected.filter(
    (field, index) => collected.findIndex((one) => one.name === field.name) === index
  )
})

const groups = computed(() => fieldGroups(activeFields.value))
// One tab is not a choice, so the strip only appears once there are two.
const showTabs = computed(() => groups.value.length > 1)
const activeGroup = ref("general")

const secretPlaceholder = computed(() => (isEdit.value ? "Leave unchanged" : undefined))
const saving = computed(() => createConnector.isPending.value || updateConnector.isPending.value)

/** The address, asked of the server whenever the values could compose one. */
let describeToken = 0
async function describe() {
  if (!typeName.value || !shape.value) return
  if (!fieldsToZod(activeFields.value).safeParse(optionValues.value).success) {
    // Half-typed values would only produce a half-built address.
    connectionString.value = ""
    return
  }
  const token = ++describeToken
  try {
    const answer = await describeDraft.mutateAsync({
      adapter_type: typeName.value,
      options: filledOptions(),
      connector_id: saved.value?.id ?? null,
    })
    // A later edit already asked; its answer is the current one.
    if (token !== describeToken) return
    connectionString.value = answer.connection_string
    hasConnectionString.value = true
  } catch (error) {
    if (token !== describeToken) return
    connectionString.value = ""
    // 501 means this kind of source has no address at all, which is an answer
    // and not a failure: the row simply does not appear.
    hasConnectionString.value = false
    void error
  }
}

let describeTimer: ReturnType<typeof setTimeout> | undefined
watch([optionValues, typeName], () => {
  clearTimeout(describeTimer)
  describeTimer = setTimeout(describe, 400)
})

function load() {
  checkResult.value = null
  nameError.value = ""
  connectionString.value = ""
  hasConnectionString.value = null
  dirty.value = false
  saved.value = props.connector
  if (props.connector) {
    name.value = props.connector.name
    resetOptions(allFields.value, props.connector.config as Record<string, unknown>)
  } else {
    name.value = ""
    resetOptions(allFields.value)
  }
  describe()
}

// The schema arrives with the list of types, which may still be loading when
// the window opens; the form is filled in as soon as it is there.
watch([() => props.connector, selectedSchema], load, { immediate: true })
watch(dirty, (value) => emit("update:dirty", value))
watch([name, optionValues], () => {
  dirty.value = true
})
watch(groups, (list) => {
  if (!list.some((group) => group.id === activeGroup.value)) {
    activeGroup.value = list[0]?.id ?? "general"
  }
})

function filledOptions(): Record<string, unknown> {
  // An empty secret is not sent: the server keeps the stored value.
  const result: Record<string, unknown> = {}
  // Only the fields of the chosen variant: a password typed before switching
  // to a way of connecting that has none is kept on screen, not sent.
  for (const field of activeFields.value) {
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
  if (!typeName.value) return
  checkResult.value = null
  try {
    checkResult.value = await checkDraft.mutateAsync({
      adapter_type: typeName.value,
      options: filledOptions(),
      connector_id: saved.value?.id ?? null,
    })
    // The dot beside the connection reads this, and it is the only check
    // there is: the same values, exercised the same way.
    if (saved.value) checks.record(saved.value.id, checkResult.value.ok)
  } catch (error) {
    const serverErrors = fieldErrorsFrom(error)
    if (serverErrors) applyServerErrors(serverErrors)
    else toast.error(messageOf(error, "Could not reach the server"))
  }
}

/** Save and stay. Returns whether it worked, so OK can close on success. */
async function apply(): Promise<boolean> {
  if (!typeName.value || !shape.value) return false
  const nameValid = validateName()
  // While editing an empty password is allowed, so the schema is enforced in
  // full only for a connection being created.
  const valuesValid = isEdit.value ? true : validateOptions(fieldsToZod(activeFields.value))
  if (!nameValid || !valuesValid) return false

  try {
    if (saved.value) {
      await updateConnector.mutateAsync({
        connectorId: saved.value.id,
        body: { name: name.value, options: filledOptions() },
      })
    } else {
      const created = await createConnector.mutateAsync({
        name: name.value,
        adapter_type: typeName.value,
        options: filledOptions(),
      })
      // From here on this is that connection's window, so a second Apply
      // updates it rather than creating a second one. See O7.
      saved.value = created
      emit("created", created)
    }
    dirty.value = false
    toast.success("Connection saved")
    return true
  } catch (error) {
    const serverErrors = fieldErrorsFrom(error)
    if (serverErrors) applyServerErrors(serverErrors)
    else toast.error(messageOf(error, "Could not reach the server"))
    return false
  }
}

async function ok() {
  if (await apply()) emit("close")
}

async function remove() {
  const connector = saved.value
  if (!connector) return

  const answer = await confirm({
    title: "Delete connection",
    message: `The connection "${connector.name}" will be deleted permanently.`,
    confirmLabel: "Delete",
    danger: true,
  })
  if (!answer) return

  await removeConnector.mutateAsync(connector.id)
  // The dot outlives the row otherwise: a record nobody prunes is a record
  // that grows for as long as the page lives.
  checks.forget(connector.id)
  dirty.value = false
  toast.success("Connection deleted")
  emit("close")
}

async function copyUrl() {
  await navigator.clipboard.writeText(connectionString.value)
  toast.success("Connection string copied")
}

/**
 * Take what is on the clipboard apart into the fields.
 *
 * A button rather than an editable field: one control that sometimes shows
 * what was composed and sometimes takes what was typed would have to answer
 * "which of the two is true now", and the answer here is settled — the fields
 * are. The way of connecting comes back with the rest, decided by the driver.
 */
async function pasteUrl() {
  if (!typeName.value) return
  let text = ""
  try {
    text = await navigator.clipboard.readText()
  } catch {
    toast.error("Could not read the clipboard")
    return
  }

  try {
    const answer = await parseUrl.mutateAsync({ adapter_type: typeName.value, url: text })
    resetOptions(allFields.value, answer.options as Record<string, unknown>)
    dirty.value = true
    toast.success("Connection string read into the form")
  } catch (error) {
    toast.error(messageOf(error, "That is not a connection string this source reads"))
  }
}
</script>

<template>
  <div class="connector-window">
    <AppSpinner v-if="adapterTypes.isLoading.value" />

    <template v-else>
      <div class="connector-window__body">
        <AppInput
          v-model="name"
          label="Name"
          data-testid="connector-name"
          :error="nameError"
        />

        <!-- The type, stated rather than offered: it was chosen in the
             catalog, and it never changes afterwards. -->
        <div
          v-if="selectedType"
          class="connector-window__type"
          data-testid="connector-type"
        >
          <span class="connector-window__label">Driver:</span>
          <q-icon
            :name="adapterIcon(selectedType.name)"
            size="22px"
          />
          <span>{{ selectedType.title }}</span>
          <span class="connector-window__muted">{{ selectedType.category_title }}</span>
        </div>

        <!-- Only once the server names a second group: one tab is not a
             choice, and a strip of one would say nothing. -->
        <div
          v-if="showTabs"
          class="connector-window__tabs"
          data-testid="connector-tabs"
        >
          <button
            v-for="group in groups"
            :key="group.id"
            type="button"
            class="connector-window__tab"
            :class="{ 'connector-window__tab--active': group.id === activeGroup }"
            :data-testid="`connector-tab-${group.id}`"
            @click="activeGroup = group.id"
          >
            {{ group.id }}
          </button>
        </div>

        <SchemaFields
          v-for="group in groups"
          v-show="!showTabs || group.id === activeGroup"
          :key="group.id"
          v-model="optionValues"
          :fields="group.fields"
          :errors="optionErrors"
          :secret-placeholder="secretPlaceholder"
        />

        <ConnectionCheck :result="checkResult" />
      </div>

      <!-- Pinned above the buttons rather than left at the end of the
           scrolling form: it is composed from every field above it, so it is
           worth reading whichever field is being edited. Shown and not
           edited — the "URL only" mode belongs to the next sub-project. A
           source with no such address answers 501 and gets no row at all. -->
      <div
        v-if="hasConnectionString !== false"
        class="connector-window__url"
      >
        <AppInput
          :model-value="connectionString"
          label="URL"
          data-testid="connector-url"
          :disable="true"
        />
        <AppIconButton
          icon="content_copy"
          tooltip="Copy the connection string. The password is not part of it."
          data-testid="copy-url"
          :disable="connectionString === ''"
          @click="copyUrl"
        />
        <!-- The other direction: what is on the clipboard, taken apart by the
             driver into these very fields. -->
        <AppIconButton
          icon="content_paste_go"
          tooltip="Paste a connection string and fill the fields from it."
          data-testid="paste-url"
          :loading="parseUrl.isPending.value"
          @click="pasteUrl"
        />
      </div>

      <footer class="connector-window__foot">
        <AppButton
          variant="secondary"
          label="Test Connection"
          data-testid="check-draft"
          :disable="!typeName"
          :loading="checkDraft.isPending.value"
          @click="check"
        />
        <AppButton
          v-if="isEdit"
          variant="danger-quiet"
          label="Delete"
          data-testid="delete-connector"
          :loading="removeConnector.isPending.value"
          @click="remove"
        />
        <span class="connector-window__spacer" />
        <AppButton
          label="OK"
          data-testid="save-connector"
          :disable="!typeName"
          :loading="saving"
          @click="ok"
        />
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
          data-testid="cancel-connector"
          @click="emit('close')"
        />
        <!-- Saves and stays: the reason several of these windows are open at
             once is to keep working in them. -->
        <AppButton
          variant="secondary"
          label="Apply"
          data-testid="apply-connector"
          :disable="!typeName"
          :loading="saving"
          @click="apply"
        />
      </footer>
    </template>
  </div>
</template>

<style scoped>
.connector-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.connector-window__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 12px 16px;
}
.connector-window__type {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.connector-window__label {
  opacity: 0.7;
}
.connector-window__muted {
  font-size: 12px;
  opacity: 0.6;
}
.connector-window__tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.3);
}
.connector-window__tab {
  border: none;
  background: none;
  padding: 6px 12px;
  cursor: pointer;
  text-transform: capitalize;
  border-bottom: 2px solid transparent;
  color: inherit;
  font: inherit;
}
.connector-window__tab--active {
  border-bottom-color: var(--q-primary);
  font-weight: 500;
}
.connector-window__url {
  flex: none;
  display: flex;
  align-items: flex-end;
  gap: 4px;
  min-width: 0;
  padding: 0 16px 8px;
  border-top: 1px solid rgba(128, 128, 128, 0.3);
}
.connector-window__url > *:first-child {
  flex: 1;
  min-width: 0;
}
.connector-window__foot {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-top: 1px solid rgba(128, 128, 128, 0.3);
}
.connector-window__spacer {
  flex: 1;
}
</style>
