<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ConnectionCheckReport, ConnectorDraft, ConnectorPublic, SshKeyPublic } from "@/client"
import { ACCESS_LABELS } from "@/features/connectors/access"
import ConnectionCheck from "@/features/connectors/ConnectionCheck.vue"
import AccessRequests from "@/features/shares/AccessRequests.vue"
import GrantList from "@/features/shares/GrantList.vue"
import ShareDialog from "@/features/shares/ShareDialog.vue"
import {
  useAdapterTypes,
  useCheckConnector,
  useCheckDraft,
  useCreateConnector,
  useDeleteConnector,
  useDescribeDraft,
  useParseUrl,
  useUpdateConnector,
} from "@/features/connectors/api"
import {
  cacheWindowNote,
  cacheWindowOf,
  cacheWindowOptions,
  cacheWindowValue,
  windowApplies,
} from "@/features/connectors/cacheWindow"
import { mergeParsedOptions } from "@/features/connectors/parsedOptions"
import { windowPages } from "@/features/connectors/windowPages"
import ServerKeyField from "@/features/sshKeys/ServerKeyField.vue"
import SshKeyDialog from "@/features/sshKeys/SshKeyDialog.vue"
import UnlockKeyDialog from "@/features/sshKeys/UnlockKeyDialog.vue"
import { useSshKeys } from "@/features/sshKeys/api"
import { withKeyChoices } from "@/features/sshKeys/keys"
import { fieldErrorsFrom, messageOf, statusOf } from "@/shared/api/errors"
import { copyText } from "@/shared/clipboard"
import SchemaFields from "@/shared/SchemaForm/SchemaFields.vue"
import {
  DEFAULT_GROUP,
  fieldGroups,
  fieldsToZod,
  readSchema,
} from "@/shared/SchemaForm/jsonSchema"
import type { FieldSpec, JsonSchema } from "@/shared/SchemaForm/jsonSchema"
import { useSchemaForm } from "@/shared/SchemaForm/useSchemaForm"
import {
  AppButton,
  AppColorPicker,
  AppCopyButton,
  AppInput,
  AppPopup,
  AppForm,
  AppSelect,
  AppSpinner,
  AppTabs,
  AppToggle,
  AppTooltip,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { useKeepState } from "@/features/searchIndex/api"
import { useSearchIndexWindow } from "@/features/searchIndex/searchIndexWindow"
import { statusLine } from "@/features/searchIndex/state"
import { useServices } from "@/features/services/api"
import { useConnectorChecksStore } from "@/stores/connectorChecks"

/**
 * One connection, in a window of its own; laid out after the spec, O6 to O9.
 *
 * Several are open at once, so nothing here may assume it is the only one:
 * everything it reads goes through vue-query, and everything it changes it
 * reports upwards.
 */
const props = defineProps<{
  /** The stored connection, or null for one being created. */
  connector: ConnectorPublic | null
  /** The type chosen in the catalog; used only while creating. */
  adapterType: string | null
  /** Source-prepared defaults for a new connection, still editable before saving. */
  draft?: ConnectorDraft
  /**
   * The page to open on, when the window is opened for something in
   * particular: answering a request for access arrives at the page where
   * access is given (D61). Absent means the address, which is what a window
   * opened to look at a connection is about.
   */
  startOn?: string
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
const checkStored = useCheckConnector()
const checking = computed(() => checkDraft.isPending.value || checkStored.isPending.value)
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
const tabColor = ref<string | null>(null)
const enabled = ref(true)
/**
 * How far a console may go through this connection (D66).
 *
 * A property of the connection and not of a session, because it answers a
 * question about the source itself — whether anybody may write to it from
 * here at all. Confirmation is the middle setting and the default: writing is
 * possible, and never without somebody saying so first.
 */
/**
 * How long answers read through this connection may be reused.
 *
 * A property of the connection because the answer depends on the data, not on
 * the driver: a nightly reporting replica and a queue table somebody is
 * watching are both PostgreSQL, and the source's one guess is wrong for both.
 * Null leaves it to the source (D105).
 */
const cacheWindow = ref<number | null>(null)

function chooseCacheWindow(value: unknown) {
  const chosen = cacheWindowOf(value)
  if (chosen !== undefined) cacheWindow.value = chosen
}

type ExecutionPolicy = ConnectorPublic["execution_policy"]
const executionPolicy = ref<ExecutionPolicy>("confirm_writes")
const POLICY_OPTIONS: { label: string; value: ExecutionPolicy }[] = [
  { label: "Read only", value: "read_only" },
  { label: "Ask before writing", value: "confirm_writes" },
  { label: "Writing allowed", value: "allow_writes" },
]

/** What the chosen policy means, said under the choice as its help. */
const policyNote = computed(() =>
  executionPolicy.value === "read_only"
    ? "Consoles on this connection can only read."
    : executionPolicy.value === "allow_writes"
      ? "Consoles on this connection can write."
      : "Each write asks for confirmation before it runs."
)

function choosePolicy(value: unknown) {
  if (POLICY_OPTIONS.some((option) => option.value === value)) {
    executionPolicy.value = value as ExecutionPolicy
  }
}

/** Whether data read through this connection may leave the server (D135). */
const thirdPartyTransfer = ref(false)
const nameError = ref("")
const checkResult = ref<ConnectionCheckReport | null>(null)
const checkPopupOpen = ref(false)
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
  return JSON.stringify([
    name.value,
    tabColor.value,
    enabled.value,
    executionPolicy.value,
    thirdPartyTransfer.value,
    cacheWindow.value,
    ordered,
  ])
}

const dirty = computed(() => snapshot() !== baseline.value)

// The saved connection this window is on. Held here rather than read off the
// prop so that Apply on a new connection turns this into an edit window
// without the parent having to re-create the component. See O7.
const saved = ref<ConnectorPublic | null>(null)

const isEdit = computed(() => saved.value !== null)

/**
 * The service this server started for this connection, if it started one.
 *
 * Read from the services rather than marked on the connector: both lists are
 * already here, and a connection that came from a service is a connection like
 * any other everywhere else (D83).
 */
const services = useServices()
const ownService = computed(
  () =>
    (services.data.value ?? []).find(
      (service) => service.connector_id === saved.value?.id
    ) ?? null
)

/**
 * What this window may do to the connection it is on.
 *
 * A connection that is not saved yet is the caller's own: they are creating
 * it. A stored one says for itself (D33), so nothing here derives a right
 * from who is signed in.
 */
const access = computed(() => saved.value?.access ?? "own")
const isOwner = computed(() => access.value === "own")
/**
 * Shown, and not editable.
 *
 * A grant is access to the source, not to the record of how to reach it: the
 * options and the credentials stay the owner's. The form is disabled rather
 * than hidden, because seeing what one is connected to — which host, which
 * database — is part of what reading it means. Testing the connection stays
 * available: it opens nothing this window does not already read.
 */
const readOnly = computed(() => isEdit.value && !isOwner.value)

/**
 * What the search keeps of this connection, said here and changed in its own
 * window, which the catalog's Actions menu opens too (D212).
 */
const keepState = useKeepState(computed(() => saved.value?.id ?? null))
const searchIndexWindow = useSearchIndexWindow()

function openSearchIndex() {
  const connector = saved.value
  if (connector) searchIndexWindow.open({ id: connector.id, name: connector.name })
}
/**
 * The stored connection a draft takes its secrets from: only one's own.
 *
 * Every other option in a draft is the caller's, the host included, so the
 * server refuses anybody else (D33). A grantee's form describes what it shows
 * without them and checks the connection as stored.
 */
const secretsFrom = computed(() => (readOnly.value ? null : (saved.value?.id ?? null)))
const sharing = ref(false)
const typeName = computed(() => saved.value?.adapter_type ?? props.adapterType ?? null)

const selectedType = computed(
  () => (adapterTypes.data.value ?? []).find((item) => item.name === typeName.value) ?? null
)

const selectedSchema = computed<JsonSchema | null>(
  () => (selectedType.value?.options_schema as unknown as JsonSchema | undefined) ?? null
)

// What this kind of source keeps its own answers for, so the field that
// offers to change it can say what it would be changing. Undefined while the
// types are still loading, null for a source that keeps nothing (D105).
const sourceWindows = computed(() => selectedType.value?.cache_windows)

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

// The owner's SSH keys, asked for only by a form with a field to put one in
// (D146): the choice is theirs, and the schema says only what the field holds.
const wantsKeys = computed(() => allFields.value.some((field) => field.purpose === "ssh-key"))
const sshKeys = useSshKeys(wantsKeys)

const groups = computed(() =>
  fieldGroups(withKeyChoices(activeFields.value, sshKeys.data.value ?? []))
)

/** The key this form signs in with, when it signs in with one of the owner's. */
const formKey = computed<SshKeyPublic | null>(() => {
  const field = activeFields.value.find((one) => one.purpose === "ssh-key")
  const chosen = field === undefined ? undefined : optionValues.value[field.name]
  return (sshKeys.data.value ?? []).find((key) => key.id === chosen) ?? null
})
/** A key that answered "locked", being opened from here (D147). */
const unlocking = ref<SshKeyPublic | null>(null)
/** Making or importing a key without leaving for Preferences (D146). */
const makingKey = ref<"generate" | "import" | null>(null)
/**
 * Point this form at the key just made for it, when it points at none yet:
 * the choice list re-reads itself on the mutation, so the id lands on it.
 */
function takeKey(id: string) {
  // A connection only shared with this person stays as its owner left it;
  // the key is theirs all the same, in Preferences and every other form.
  if (readOnly.value) return
  const field = activeFields.value.find((one) => one.purpose === "ssh-key")
  if (field && !optionValues.value[field.name]) {
    optionValues.value = { ...optionValues.value, [field.name]: id }
  }
}
const pages = computed(() => windowPages(groups.value))
const activePage = ref(props.startOn ?? DEFAULT_GROUP)
/**
 * Whose page is showing: the source's own fields, or one of the two this
 * application owns.
 *
 * What follows from it is more than which block is drawn: the connection
 * string belongs to the address, so it shows on the source's pages and goes
 * away with the fields it is composed from.
 */
const pageOwner = computed(
  () => pages.value.find((page) => page.id === activePage.value)?.owner ?? "source"
)
const onSource = computed(() => pageOwner.value === "source")
const onOptions = computed(() => pageOwner.value === "options")
const onPermissions = computed(() => pageOwner.value === "permissions")

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

/**
 * The address, asked of the server whenever the values change — including
 * while the form is still being filled in, since the defaults already put a
 * host and a port there.
 *
 * Composing it here would be a second implementation of a grammar that belongs
 * to the driver, and the two would differ in the quoting before they differed
 * in anything visible.
 */
let describeToken = 0
async function describe() {
  if (!typeName.value || !shape.value) return
  const token = ++describeToken
  try {
    const answer = await describeDraft.mutateAsync({
      adapter_type: typeName.value,
      options: filledOptions(),
      connector_id: secretsFrom.value,
    })
    // A later edit already asked; its answer is the current one.
    if (token !== describeToken) return
    connectionString.value = answer.connection_string
    if (!urlFocused.value) urlText.value = answer.connection_string
    hasConnectionString.value = true
  } catch (error) {
    if (token !== describeToken) return
    // 501 means this kind of source has no address at all, which is an answer
    // and not a failure: the row simply does not appear. Anything else is a
    // request that did not arrive, and a row taken away because the network
    // blinked would be this screen inventing an answer of its own.
    if (statusOf(error) !== 501) return
    connectionString.value = ""
    hasConnectionString.value = false
  }
}

let describeTimer: ReturnType<typeof setTimeout> | undefined
watch([optionValues, typeName], () => {
  clearTimeout(describeTimer)
  describeTimer = setTimeout(describe, 400)
})

function load() {
  checkResult.value = null
  checkPopupOpen.value = false
  nameError.value = ""
  connectionString.value = ""
  urlText.value = ""
  urlError.value = ""
  hasConnectionString.value = null
  saved.value = props.connector
  if (props.connector) {
    name.value = props.connector.name
    tabColor.value = props.connector.tab_color ?? null
    enabled.value = props.connector.enabled
    executionPolicy.value = props.connector.execution_policy
    thirdPartyTransfer.value = props.connector.allow_third_party_transfer
    cacheWindow.value = props.connector.cache_ttl_seconds ?? null
    resetOptions(allFields.value, props.connector.config as Record<string, unknown>)
  } else {
    // A source action supplies the node's name and options; otherwise the
    // chosen type gives a new connection its initial name.
    name.value = props.draft?.name ?? selectedType.value?.title ?? ""
    tabColor.value = null
    enabled.value = true
    executionPolicy.value = "confirm_writes"
    thirdPartyTransfer.value = false
    cacheWindow.value = null
    resetOptions(allFields.value, props.draft?.options)
  }
  baseline.value = snapshot()
  describe()
}

// The schema arrives with the list of types, which may still be loading when
// the window opens; the form is filled in as soon as it is there.
watch([() => props.connector, () => props.draft, selectedSchema], load, { immediate: true })
watch(dirty, (value) => emit("update:dirty", value), { immediate: true })
// A page can go: switching the way of connecting replaces the source's groups,
// and Apply on a new connection adds the settings page under the same window.
watch(pages, (list) => {
  if (!list.some((page) => page.id === activePage.value)) {
    activePage.value = list[0]?.id ?? DEFAULT_GROUP
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
  checkPopupOpen.value = false
  try {
    checkResult.value =
      readOnly.value && saved.value
        ? await checkStored.mutateAsync(saved.value.id)
        : await checkDraft.mutateAsync({
            adapter_type: typeName.value,
            options: filledOptions(),
            connector_id: secretsFrom.value,
          })
    checkPopupOpen.value = true
    // The dot beside the connection reads this. A draft is checked with the
    // values in the form, which may differ from the stored ones, so this is
    // recorded here rather than left to the monitor.
    if (saved.value) {
      checks.record(saved.value.id, {
        ok: checkResult.value.ok,
        message: checkResult.value.message,
        latencyMs: checkResult.value.latency_ms ?? null,
        checkedAt: new Date().toISOString(),
      })
    }
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
      saved.value = await updateConnector.mutateAsync({
        connectorId: saved.value.id,
        body: {
          name: name.value,
          tab_color: tabColor.value,
          enabled: enabled.value,
          execution_policy: executionPolicy.value,
          allow_third_party_transfer: thirdPartyTransfer.value,
          // Always sent, null included: the server tells an omitted field
          // from an explicit null, and null is the answer that hands the
          // window back to the source (D105).
          cache_ttl_seconds: cacheWindow.value,
          options: filledOptions(),
        },
      })
    } else {
      const created = await createConnector.mutateAsync({
        name: name.value,
        tab_color: tabColor.value,
        adapter_type: typeName.value,
        options: filledOptions(),
        execution_policy: executionPolicy.value,
        allow_third_party_transfer: thirdPartyTransfer.value,
        cache_ttl_seconds: cacheWindow.value,
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

  // A connection this server started a container for is only half the thing:
  // deleting it never touches the container or its data, and saying so is the
  // difference between a promise kept and a surprise (D84).
  const started = ownService.value
  const answer = await confirm({
    title: "Delete connection",
    message: started
      ? `The connection "${connector.name}" will be deleted permanently. ` +
        "The service this server started for it keeps running, with its data; " +
        "remove the service itself to take that away."
      : `The connection "${connector.name}" will be deleted permanently.`,
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
  await copyText(urlText.value)
  toast.success("Connection string copied")
}

/**
 * An address typed into the URL box, taken apart into the fields.
 *
 * The box keeps no answer of its own: what is typed goes to the driver, the
 * driver produces fields, and the fields compose the string that comes back.
 * A password typed into the box therefore lands in the password field and
 * leaves the box. Delayed because it is a request, and not made at all for
 * text the server itself composed.
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
    optionValues.value = mergeParsedOptions({
      shape: shape.value,
      fields: allFields.value,
      current: optionValues.value,
      parsed: answer.options as Record<string, unknown>,
      secretsAreStored: secretsAreStored.value,
    })
    urlError.value = ""
  } catch (error) {
    urlError.value = messageOf(error, "That is not a connection string this source reads")
  }
}
</script>

<template>
  <AppForm class="connector-window">
    <AppSpinner v-if="adapterTypes.isLoading.value" />

    <template v-else>
      <div class="connector-window__navigation">
        <div class="connector-window__heading">
          <AppInput
            v-model="name"
            class="connector-window__name"
            label="Name"
            data-testid="connector-name"
            :disable="readOnly"
            :error="nameError"
          >
            <template #after>
              <AppColorPicker
                v-model="tabColor"
                label="Tab color"
                data-testid="connector-tab-color"
                :disable="readOnly"
              />
            </template>
          </AppInput>
          <!-- Only for a connection that exists: there is nothing to switch
               off before it is saved, and the row would ask a question about
               a thing that is not there yet. -->
          <span
            v-if="saved"
            class="connector-window__enabled"
          >
            <AppToggle
              v-model="enabled"
              label="In use"
              data-testid="connector-enabled"
              :disable="readOnly"
            />
            <AppTooltip>
              Switch off to keep this connection saved but unavailable for data access. Automatic health checks also stop.
            </AppTooltip>
          </span>
        </div>

        <!-- Always three pages at least: how to reach the connection, how it
             behaves once reached, and what may be done through it. -->
        <AppTabs
          v-model="activePage"
          :options="pages.map((page) => ({ value: page.id, label: page.label }))"
          class="connector-window__tabs"
          data-testid="connector-tabs"
        />
      </div>

      <div
        class="connector-window__body"
        data-testid="connector-body"
      >
        <SchemaFields
          v-for="group in groups"
          v-show="group.id === activePage"
          :key="group.id"
          v-model="optionValues"
          :fields="group.fields"
          :errors="optionErrors"
          :secrets-are-stored="secretsAreStored"
          :disable="readOnly"
        >
          <template #field-ssh-host-key="{ value, update, disable }">
            <ServerKeyField
              :adapter-type="typeName ?? ''"
              :options="optionValues"
              :model-value="typeof value === 'string' ? value : ''"
              :disable="disable"
              @update:model-value="update"
            />
          </template>
        </SchemaFields>

        <!-- How this connection behaves, away from how to reach it and from
             who may reach it. Nobody's first question, and nobody has to see
             it to make a connection work: how long an answer may be reused is
             a property of the data behind the connection, and only its owner
             knows whether that data changes nightly or every second (D105). -->
        <div
          v-show="onOptions"
          class="connector-window__options"
          data-testid="connector-options"
        >
          <AppSelect
            class="connector-window__cache"
            :model-value="cacheWindowValue(cacheWindow)"
            :options="cacheWindowOptions(sourceWindows)"
            label="Keep answers"
            :hint="cacheWindowNote(cacheWindow, sourceWindows)"
            :disable="readOnly || !windowApplies(sourceWindows)"
            data-testid="connector-cache-window"
            @update:model-value="chooseCacheWindow"
          />
          <section
            v-if="isEdit && keepState.data.value"
            class="connector-window__search-index"
          >
            <span
              class="dp-helper"
              data-testid="connector-search-index"
            >
              Search index: {{
                keepState.data.value.available
                  ? statusLine(keepState.data.value)
                  : "this kind of source cannot keep its names"
              }}
            </span>
            <AppButton
              v-if="keepState.data.value.available"
              variant="quiet"
              size="sm"
              label="Search index…"
              @click="openSearchIndex"
            />
          </section>
          <!-- A key made or imported without leaving for Preferences (D146),
               in every connection window: keys belong to the person, not to
               the source. Where the form takes one, the choice above
               re-reads itself, and a new key for this connection is pointed
               at it. -->
          <section class="connector-window__ssh-keys">
            <h3 class="connector-window__heading-3 dp-section-title">
              SSH keys
            </h3>
            <span class="dp-helper">
              Keys your SSH connections sign in with, usable anywhere. A key
              made here never leaves this server: copy its public key into
              authorized_keys on the servers it should open.
            </span>
            <div class="connector-window__ssh-keys-buttons">
              <AppButton
                :icon="appIcons.createSshKey"
                label="New key"
                data-testid="connector-ssh-key-new"
                @click="makingKey = 'generate'"
              />
              <AppButton
                variant="quiet"
                :icon="appIcons.importSshKey"
                label="Import"
                data-testid="connector-ssh-key-import"
                @click="makingKey = 'import'"
              />
            </div>
          </section>
        </div>

        <!-- Who may reach this connection and what may be done through it,
             away from how to reach it: beside the host and the port a policy
             reads as a connection parameter, and it is not one (D66, D135).
             Everything here is the owner's: a person given access does not
             widen their own. -->
        <div
          v-show="onPermissions"
          class="connector-window__permissions"
          data-testid="connector-permissions"
        >
          <div
            v-if="!readOnly"
            class="connector-window__policy"
          >
            <!-- A label the label column holds (D131), and what the choice
                 means under it as every form's help is, not beside it in a
                 size and a place of its own. -->
            <AppSelect
              :model-value="executionPolicy"
              :options="POLICY_OPTIONS"
              label="Consoles"
              :hint="policyNote"
              class="connector-window__policy-select"
              data-testid="connector-policy"
              @update:model-value="choosePolicy"
            />
          </div>

          <!-- Shown to a grantee too, unlike the policy above: whether what
               they read here may be sent to an outside service is something
               they act on, and learning it from a refusal is too late. -->
          <div class="connector-window__policy">
            <AppToggle
              v-model="thirdPartyTransfer"
              label="Allow sending data to third parties"
              data-testid="connector-third-party"
              :disable="readOnly"
            />
            <span class="dp-helper">
              Data read through this connection may be sent to outside services, such as an AI model provider.
            </span>
          </div>

          <!-- Only once there is a connection to give away, and only for whom
               it belongs to: a grant does not pass on the right to grant.
               The list is here rather than behind the button, because who can
               reach a connection is a thing to know, not a thing to go and
               look up; the button is left with what it is for, which is adding
               somebody (D33). -->
          <section
            v-if="isEdit && isOwner"
            class="connector-window__grants"
          >
            <header class="connector-window__grants-head">
              <h3 class="connector-window__heading-3 dp-overline">
                Who else may reach it
              </h3>
              <AppButton
                variant="secondary"
                size="sm"
                label="Share"
                data-testid="share-connector"
                @click="sharing = true"
              />
            </header>
            <GrantList :connector-id="saved?.id ?? null" />
            <AccessRequests :connector-id="saved?.id ?? null" />
          </section>

          <!-- Whose it is and what was given. Stated in words rather than by
               the name of the level, and only when it is somebody else's: a
               line saying you own your own connection would be on every
               window. -->
          <div
            v-if="readOnly && saved"
            class="connector-window__shared"
            data-testid="connector-shared"
          >
            Shared by {{ saved.owner_email }} — you may
            {{ ACCESS_LABELS[access].toLowerCase() }}
          </div>
        </div>
      </div>

      <!-- Pinned above the buttons rather than left at the end of the
           scrolling form: it is composed from every field above it, so it is
           worth reading whichever field is being edited. Typed into as well:
           an address put here is taken apart by the driver into the fields,
           which then compose it again. A source with no such address answers
           501 and gets no row at all. -->
      <div
        v-if="hasConnectionString !== false"
        v-show="onSource"
        class="connector-window__url"
        data-testid="connector-url-row"
      >
        <AppInput
          :model-value="urlText"
          class="connector-window__url-field"
          label="URL"
          data-testid="connector-url"
          :disable="readOnly"
          :error="urlError"
          @focus="urlFocused = true"
          @blur="leaveUrl"
          @update:model-value="editUrl"
        >
          <template #after>
            <AppCopyButton
              tooltip="Copy the connection string. The password is not part of it."
              data-testid="copy-url"
              :disable="urlText === ''"
              @click="copyUrl"
            />
          </template>
        </AppInput>
      </div>

      <div class="connector-window__foot-area">
        <footer class="connector-window__foot">
          <span class="connector-window__check-anchor">
            <AppButton
              variant="secondary"
              label="Test Connection"
              data-testid="check-draft"
              :disable="!typeName"
              :loading="checking"
              @click="check"
            />
            <AppPopup
              v-model="checkPopupOpen"
              anchor="top left"
              self="bottom left"
            >
              <ConnectionCheck
                :result="checkResult"
                :source-title="selectedType?.title ?? 'Server'"
              >
                <!-- The check said the key is shut, and opening it is the way on (D147). -->
                <template
                  v-if="checkResult?.error_kind === 'locked' && formKey"
                  #action
                >
                  <AppButton
                    variant="secondary"
                    size="sm"
                    label="Unlock the key"
                    data-testid="unlock-form-key"
                    @click="unlocking = formKey"
                  />
                </template>
              </ConnectionCheck>
            </AppPopup>
          </span>
          <AppButton
            v-if="isEdit && isOwner"
            variant="danger-quiet"
            label="Delete"
            data-testid="delete-connector"
            :loading="removeConnector.isPending.value"
            @click="remove"
          />
          <span class="connector-window__spacer" />
          <!-- One group, so a narrow window wraps it whole rather than parting
               OK from Cancel; the main action last, as in every window (D186). -->
          <span class="connector-window__end">
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
              v-if="!readOnly"
              variant="secondary"
              label="Apply"
              data-testid="apply-connector"
              :disable="!typeName"
              :loading="saving"
              @click="apply"
            />
            <AppButton
              v-if="!readOnly"
              label="OK"
              data-testid="save-connector"
              :disable="!typeName"
              :loading="saving"
              @click="ok"
            />
          </span>
        </footer>
      </div>

      <ShareDialog
        v-if="saved && isOwner"
        v-model="sharing"
        :connector-id="saved.id"
      />
      <!-- Opened, the key is tried again at once: the answer on screen is
           about a key that is not locked any more. -->
      <UnlockKeyDialog
        :key-id="unlocking?.id ?? null"
        :key-name="unlocking?.name ?? ''"
        @unlocked="check"
        @close="unlocking = null"
      />
      <SshKeyDialog
        :model-value="makingKey !== null"
        :mode="makingKey ?? 'generate'"
        @update:model-value="!$event && (makingKey = null)"
        @created="takeKey"
      />
    </template>
  </AppForm>
</template>

<style scoped>
.connector-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.connector-window__heading {
  display: flex;
  align-items: flex-start;
  gap: var(--dp-space-3);
}
.connector-window__navigation {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  padding: var(--dp-space-3) var(--dp-space-4) 0;
}
/* The name takes what is left: the switch is two words wide and fixed, and a
   name box that changed width with the label beside it would jump. */
.connector-window__name {
  flex: 1;
}
.connector-window__enabled {
  display: inline-flex;
}
/* A statement about the window, not a field in it: quieter than the form and
   above it. */
.connector-window__shared {
  font-size: var(--dp-font-size-sm);
  color: var(--dp-text-muted);
}
.connector-window__permissions {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-4);
}
.connector-window__options {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-4);
}
.connector-window__search-index {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-3);
}
.connector-window__ssh-keys {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}
.connector-window__ssh-keys-buttons {
  display: flex;
  gap: var(--dp-space-2);
}
.connector-window__grants {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}
.connector-window__grants-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-2);
}
.connector-window__heading-3 {
  margin: 0;
}
.connector-window__policy {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
}
.connector-window__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-4);
  padding: var(--dp-space-3) var(--dp-space-4);
}
.connector-window__foot-area {
  flex: none;
}
.connector-window__tabs {
  padding-bottom: var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border);
}
.connector-window__url {
  flex: none;
  display: flex;
  min-width: 0;
  padding: var(--dp-space-2) var(--dp-space-4);
  border-top: 1px solid var(--dp-border);
}
.connector-window__url-field {
  flex: 1;
  min-width: 0;
}
.connector-window__foot {
  flex: none;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-4);
  border-top: 1px solid var(--dp-border);
}
.connector-window__end {
  display: flex;
  gap: var(--dp-space-2);
  margin-left: auto;
}
.connector-window__check-anchor {
  display: inline-flex;
}
.connector-window__spacer {
  flex: 1;
}
</style>
