<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { ConnectionCheckResult, ConnectorPublic } from "@/client"
import { ACCESS_LABELS } from "@/features/connectors/access"
import ConnectionCheck from "@/features/connectors/ConnectionCheck.vue"
import AccessRequests from "@/features/shares/AccessRequests.vue"
import GrantList from "@/features/shares/GrantList.vue"
import ShareDialog from "@/features/shares/ShareDialog.vue"
import {
  useAdapterTypes,
  useCheckDraft,
  useCreateConnector,
  useDeleteConnector,
  useDescribeDraft,
  useParseUrl,
  useUpdateConnector,
} from "@/features/connectors/api"
import { mergeParsedOptions } from "@/features/connectors/parsedOptions"
import { windowPages } from "@/features/connectors/windowPages"
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
  AppCopyButton,
  AppInput,
  AppSelect,
  AppSpinner,
  AppToggle,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { useServices } from "@/features/services/api"
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
const enabled = ref(true)
/**
 * How far a console may go through this connection (D66).
 *
 * A property of the connection and not of a session, because it answers a
 * question about the source itself — whether anybody may write to it from
 * here at all. Confirmation is the middle setting and the default: writing is
 * possible, and never without somebody saying so first.
 */
type ExecutionPolicy = ConnectorPublic["execution_policy"]
const executionPolicy = ref<ExecutionPolicy>("confirm_writes")
const POLICY_OPTIONS: { label: string; value: ExecutionPolicy }[] = [
  { label: "Read only", value: "read_only" },
  { label: "Ask before writing", value: "confirm_writes" },
  { label: "Writing allowed", value: "allow_writes" },
]

function choosePolicy(value: unknown) {
  if (POLICY_OPTIONS.some((option) => option.value === value)) {
    executionPolicy.value = value as ExecutionPolicy
  }
}
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
  return JSON.stringify([name.value, enabled.value, executionPolicy.value, ordered])
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
const sharing = ref(false)
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
const pages = computed(() => windowPages(groups.value))
const activePage = ref(props.startOn ?? DEFAULT_GROUP)
/**
 * Whether the page showing is the one about permissions rather than a page of
 * the source's own fields.
 *
 * What follows from it is more than which block is drawn: the connection
 * string belongs to the address, so it goes away with the fields it is
 * composed from.
 */
const onPermissions = computed(
  () => pages.value.find((page) => page.id === activePage.value)?.permissions === true
)

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
 * The address, asked of the server whenever the values change.
 *
 * Asked while the form is still being filled in, too. The defaults put a host
 * and a port there before anything is typed, and that is already an address
 * worth showing — but composing it here would be a second implementation of a
 * grammar that belongs to the driver, and the two would differ in the quoting
 * before they differed in anything visible. So the server answers with as
 * much of the address as there is, and this end only shows what comes back.
 */
let describeToken = 0
async function describe() {
  if (!typeName.value || !shape.value) return
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
  nameError.value = ""
  connectionString.value = ""
  urlText.value = ""
  urlError.value = ""
  hasConnectionString.value = null
  saved.value = props.connector
  if (props.connector) {
    name.value = props.connector.name
    enabled.value = props.connector.enabled
    executionPolicy.value = props.connector.execution_policy
    resetOptions(allFields.value, props.connector.config as Record<string, unknown>)
  } else {
    // Named after the type it connects to, so the form says which one was
    // picked without a row that only ever states it. One word to replace
    // beats an empty box, and a connection nobody renames still has a name.
    name.value = selectedType.value?.title ?? ""
    enabled.value = true
    executionPolicy.value = "confirm_writes"
    resetOptions(allFields.value)
  }
  baseline.value = snapshot()
  describe()
}

// The schema arrives with the list of types, which may still be loading when
// the window opens; the form is filled in as soon as it is there.
watch([() => props.connector, selectedSchema], load, { immediate: true })
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
  try {
    checkResult.value = await checkDraft.mutateAsync({
      adapter_type: typeName.value,
      options: filledOptions(),
      connector_id: saved.value?.id ?? null,
    })
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
      await updateConnector.mutateAsync({
        connectorId: saved.value.id,
        body: {
          name: name.value,
          enabled: enabled.value,
          execution_policy: executionPolicy.value,
          options: filledOptions(),
        },
      })
    } else {
      const created = await createConnector.mutateAsync({
        name: name.value,
        adapter_type: typeName.value,
        options: filledOptions(),
        execution_policy: executionPolicy.value,
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
  <div class="connector-window">
    <AppSpinner v-if="adapterTypes.isLoading.value" />

    <template v-else>
      <div class="connector-window__body">
        <div class="connector-window__heading">
          <AppInput
            v-model="name"
            class="connector-window__name"
            label="Name"
            data-testid="connector-name"
            :disable="readOnly"
            :error="nameError"
          />
          <!-- Only for a connection that exists: there is nothing to switch
               off before it is saved, and the row would ask a question about
               a thing that is not there yet. -->
          <AppToggle
            v-if="saved"
            v-model="enabled"
            label="In use"
            data-testid="connector-enabled"
            :disable="readOnly"
          />
        </div>

        <!-- Always two pages at least: how to reach the connection, and what
             may be done through it once it is reached. -->
        <div
          class="connector-window__tabs"
          data-testid="connector-tabs"
        >
          <button
            v-for="page in pages"
            :key="page.id"
            type="button"
            class="connector-window__tab"
            :class="{ 'connector-window__tab--active': page.id === activePage }"
            :data-testid="`connector-tab-${page.id}`"
            @click="activePage = page.id"
          >
            {{ page.label }}
          </button>
        </div>

        <SchemaFields
          v-for="group in groups"
          v-show="group.id === activePage"
          :key="group.id"
          v-model="optionValues"
          :fields="group.fields"
          :errors="optionErrors"
          :secrets-are-stored="secretsAreStored"
          :disable="readOnly"
        />

        <!-- Who may reach this connection and what may be done through it,
             away from how to reach it: beside the host and the port a policy
             reads as a connection parameter, and it is not one — it governs
             nothing but the statements somebody types into a console (D66).
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
            <AppSelect
              :model-value="executionPolicy"
              :options="POLICY_OPTIONS"
              label="Statements from a console"
              compact
              class="connector-window__policy-select"
              data-testid="connector-policy"
              @update:model-value="choosePolicy"
            />
            <span class="connector-window__policy-note">
              {{
                executionPolicy === "read_only"
                  ? "Consoles on this connection can only read."
                  : executionPolicy === "allow_writes"
                    ? "Writing is unlocked by choosing a writing mode."
                    : "Writing asks for the name of this connection first."
              }}
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
              <h3 class="connector-window__heading-3">
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
        v-show="!onPermissions"
        class="connector-window__url"
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
            v-if="isEdit && isOwner"
            variant="danger-quiet"
            label="Delete"
            data-testid="delete-connector"
            :loading="removeConnector.isPending.value"
            @click="remove"
          />
          <span class="connector-window__spacer" />
          <AppButton
            v-if="!readOnly"
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
            v-if="!readOnly"
            variant="secondary"
            label="Apply"
            data-testid="apply-connector"
            :disable="!typeName"
            :loading="saving"
            @click="apply"
          />
        </footer>
      </div>

      <ShareDialog
        v-if="saved && isOwner"
        v-model="sharing"
        :connector-id="saved.id"
      />
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
.connector-window__heading {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
/* The name takes what is left: the switch is two words wide and fixed, and a
   name box that changed width with the label beside it would jump. */
.connector-window__name {
  flex: 1;
}
/* A statement about the window, not a field in it: quieter than the form and
   above it. */
.connector-window__shared {
  font-size: 12px;
  color: var(--dp-text-muted);
}
.connector-window__permissions {
  display: flex;
  flex-direction: column;
  gap: 18px;
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
  font-size: 12px;
  font-weight: 600;
  color: var(--dp-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.connector-window__policy {
  display: flex;
  align-items: center;
  gap: 10px;
}
.connector-window__policy-select {
  flex: 0 1 240px;
}
.connector-window__policy-note {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--dp-text-muted);
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
  min-width: 0;
  padding: 0 16px 8px;
  border-top: 1px solid var(--dp-border);
}
.connector-window__url-field {
  flex: 1;
  min-width: 0;
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
