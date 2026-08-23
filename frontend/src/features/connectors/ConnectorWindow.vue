<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ConnectionCheckResult, ConnectorPublic } from "@/client"
import ConnectionCheck from "@/features/connectors/ConnectionCheck.vue"
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
// What is in the URL box. Held apart from the composed string because the box
// is typed into as well as read: a pasted address is taken apart into the
// fields, and the fields then compose the string again — which is what makes
// the fields, and not this text, the truth.
const urlText = ref("")
const urlError = ref("")
// Whether the box is being typed into. What the fields compose is never
// written into it while it is: an address being typed out one character at a
// time would be rewritten under the cursor as each prefix parsed.
const urlFocused = ref(false)
// Null while the source has never been asked; false once it has answered 501.
const hasConnectionString = ref<boolean | null>(null)
/**
 * What the form held when it was last loaded or saved.
 *
 * `dirty` is the answer to "does it still hold that", not a flag something
 * sets. As a flag it was set by the window filling itself in: loading a
 * connection assigns the name and the values, which is a change to watch, and
 * every window then asked whether to discard changes nobody had made. A
 * question asked every time teaches people to answer it without reading.
 */
const baseline = ref("")

function snapshot(): string {
  const values = optionValues.value
  const ordered = Object.keys(values)
    .sort()
    .map((key) => [key, values[key]])
  return JSON.stringify([name.value, ordered])
}

const dirty = computed(() => snapshot() !== baseline.value)

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
 * The fields on screen: everything the chosen way of connecting shows, in the
 * order its model declared, the choice among them.
 *
 * No order is decided here. The server states it by declaring the fields —
 * the address, then how one authenticates to it, then the rest — and a rule
 * imposed at this end would quietly override that.
 */
const activeFields = computed<FieldSpec[]>(() => {
  const current = shape.value
  if (!current) return []
  if (current.kind === "plain") return current.fields
  return current.byVariant[variantTag.value ?? ""] ?? []
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
  const collected = Object.values(current.byVariant).flat()
  return collected.filter(
    (field, index) => collected.findIndex((one) => one.name === field.name) === index
  )
})

const groups = computed(() => fieldGroups(activeFields.value))
// One tab is not a choice, so the strip only appears once there are two.
const showTabs = computed(() => groups.value.length > 1)
const activeGroup = ref("general")

// A stored connection has secrets the server will never send back, so an
// untouched secret field stands in for a value this screen does not hold.
const secretsAreStored = computed(() => isEdit.value)

/**
 * What the values must satisfy before the server is asked anything.
 *
 * While editing, a secret left untouched is not missing: the server has it
 * and fills it in. Stated once here rather than at each of the three call
 * sites, which is how the connection string came to be missing from an edit
 * window — the guard demanded a password that was never going to be typed.
 */
function draftSchema() {
  const fields = secretsAreStored.value
    ? activeFields.value.map((field) =>
        field.kind === "password" ? { ...field, required: false, minLength: 0 } : field
      )
    : activeFields.value
  return fieldsToZod(fields)
}
const saving = computed(() => createConnector.isPending.value || updateConnector.isPending.value)

/** The address, asked of the server whenever the values could compose one. */
let describeToken = 0
async function describe() {
  if (!typeName.value || !shape.value) return
  if (!draftSchema().safeParse(optionValues.value).success) {
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
    if (!urlFocused.value) urlText.value = answer.connection_string
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
  urlText.value = ""
  urlError.value = ""
  hasConnectionString.value = null
  saved.value = props.connector
  if (props.connector) {
    name.value = props.connector.name
    resetOptions(allFields.value, props.connector.config as Record<string, unknown>)
  } else {
    // Named after the type it connects to, so the form says which one was
    // picked without a row that only ever states it. One word to replace
    // beats an empty box, and a connection nobody renames still has a name.
    name.value = selectedType.value?.title ?? ""
    resetOptions(allFields.value)
  }
  baseline.value = snapshot()
  describe()
}

// The schema arrives with the list of types, which may still be loading when
// the window opens; the form is filled in as soon as it is there.
watch([() => props.connector, selectedSchema], load, { immediate: true })
watch(dirty, (value) => emit("update:dirty", value), { immediate: true })
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
  const valuesValid = validateOptions(draftSchema())
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
    // Saved is the new baseline: what is on screen is what is stored.
    baseline.value = snapshot()
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
  // Nothing left to discard, so closing must not ask about it.
  baseline.value = snapshot()
  toast.success("Connection deleted")
  emit("close")
}

async function copyUrl() {
  await navigator.clipboard.writeText(urlText.value)
  toast.success("Connection string copied")
}

/**
 * An address typed into the URL box, taken apart into the fields.
 *
 * The box answers "which of the two is true now" by never keeping an answer
 * of its own: what is typed goes to the driver, the driver produces fields,
 * and the fields compose the string that comes back. A password typed into
 * the box therefore lands in the password field and leaves the box, which is
 * the rule made visible rather than explained.
 *
 * Delayed, because it is a request, and it is not made at all for text the
 * server itself composed.
 */
let parseTimer: ReturnType<typeof setTimeout> | undefined

function editUrl(text: string) {
  urlText.value = text
  urlError.value = ""
  clearTimeout(parseTimer)
  parseTimer = setTimeout(() => void parseTyped(text), 600)
}

/** Leaving the box hands it back to the fields, whatever was typed into it. */
function leaveUrl() {
  urlFocused.value = false
  clearTimeout(parseTimer)
  void parseTyped(urlText.value).then(() => {
    if (connectionString.value !== "") urlText.value = connectionString.value
  })
}

async function parseTyped(text: string) {
  if (!typeName.value) return
  // Nothing to take apart, and nothing to say about it: an emptied box is on
  // its way somewhere, not a refusal.
  if (text.trim() === "" || text === connectionString.value) return

  try {
    const answer = await parseUrl.mutateAsync({ adapter_type: typeName.value, url: text })
    resetOptions(allFields.value, answer.options as Record<string, unknown>)
  } catch (error) {
    urlError.value = messageOf(error, "That is not a connection string this source reads")
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
          :secrets-are-stored="secretsAreStored"
        />
      </div>

      <!-- Pinned above the buttons rather than left at the end of the
           scrolling form: it is composed from every field above it, so it is
           worth reading whichever field is being edited. Typed into as well:
           an address put here is taken apart by the driver into the fields,
           which then compose it again. A source with no such address answers
           501 and gets no row at all. -->
      <div
        v-if="hasConnectionString !== false"
        class="connector-window__url"
      >
        <AppInput
          :model-value="urlText"
          label="URL"
          data-testid="connector-url"
          :error="urlError"
          @focus="urlFocused = true"
          @blur="leaveUrl"
          @update:model-value="editUrl"
        />
        <AppIconButton
          icon="content_copy"
          tooltip="Copy the connection string. The password is not part of it."
          data-testid="copy-url"
          :disable="urlText === ''"
          @click="copyUrl"
        />
      </div>

      <!-- The result of the last check floats over this strip rather than
           sitting in the form: it is read once and dismissed, and a line in
           the body moved every field below it. -->
      <div class="connector-window__foot-area">
        <ConnectionCheck
          :result="checkResult"
          @close="checkResult = null"
        />

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
      </div>
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
.connector-window__foot-area {
  flex: none;
  position: relative;
}
.connector-window__tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--dp-border);
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
  border-top: 1px solid var(--dp-border);
}
.connector-window__url > *:first-child {
  flex: 1;
  min-width: 0;
}
/* A Quasar field reserves a line under its control for an error message, so
   aligning to the bottom of the box puts a button that height below the one
   thing it belongs to. */
.connector-window__url > button {
  margin-bottom: 20px;
}
.connector-window__foot {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-top: 1px solid var(--dp-border);
}
.connector-window__spacer {
  flex: 1;
}
</style>
