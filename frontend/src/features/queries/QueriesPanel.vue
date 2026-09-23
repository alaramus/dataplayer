<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref, watch } from "vue"

import { connectorNameOf, useConnectors } from "@/features/connectors/api"
import {
  usePurgeQueryDocument,
  useQueryDocuments,
  useRestoreQueryDocument,
  useTrashQueryDocument,
} from "@/features/queries/api"
import { emptyDraft, writeDraft } from "@/features/queries/draft"
import {
  useDeleteRuns,
  useRunHistory,
  useRunText,
} from "@/features/queries/runs"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppEmptyState,
  AppIconButton,
  AppInput,
  AppSelect,
  AppSpinner,
  useConfirm,
  useToast,
} from "@/shared/ui"

/**
 * The library of query documents (D65).
 *
 * Queries are navigation of their own rather than nodes invented inside a
 * source catalog: they belong to a person, not to a database, and one of them
 * may outlive the connection it was written against.
 */

/**
 * The three places this panel holds, and what each of them answers.
 *
 * Queries are documents somebody is writing; History is what actually ran.
 * They read alike — both are lists of SQL — so each row says which kind of
 * thing it is: a document by its name and its connection, a run by what it
 * did, when, and which document it was run from.
 */
const PLACES = [
  { value: "queries", label: "Queries", icon: appIcons.description },
  { value: "history", label: "History", icon: appIcons.history },
  { value: "trash", label: "Trash", icon: appIcons.delete },
] as const
type Place = (typeof PLACES)[number]["value"]

const props = defineProps<{ panelId: string }>()

const workspace = useWorkspaceActions()
const toast = useToast()
const confirm = useConfirm()
const connectors = useConnectors()

const connectorId = ref<string | null>(null)
const search = ref("")
/**
 * Which of the three places this panel is showing.
 *
 * One state rather than two flags that overlap. Queries are what somebody is
 * writing, Trash is what they deleted, and History is what actually ran — the
 * same person's three questions about their own queries, in the one place they
 * look for them (D63). As two booleans, pressing Trash while looking at
 * History did nothing and the button had to be greyed out to say so.
 */
const showing = ref<Place>("queries")
const trashed = computed(() => showing.value === "trash")

const filters = computed(() => ({
  connectorId: connectorId.value,
  search: search.value.trim(),
  trashed: trashed.value,
}))
const documents = useQueryDocuments(filters)
const history = useRunHistory(
  () => null,
  () => search.value.trim()
)
const runText = useRunText()
const deleteRuns = useDeleteRuns()
const trash = useTrashQueryDocument()
const restore = useRestoreQueryDocument()
const purge = usePurgeQueryDocument()

useReloadable(() => props.panelId, async () => {
  await documents.refetch()
  await history.refetch()
})

/**
 * The connection this panel was opened from, taken once.
 *
 * Watched rather than received as a prop: there is one library panel however
 * often it is opened, and the workspace binds a panel's props when the panel
 * is first drawn — so a panel already open would never see a second arrival.
 * The same arrangement every other panel target uses (D69).
 */
watch(
  workspace.queriesTarget,
  () => {
    const taken = workspace.takeQueriesTarget()
    if (taken !== null) connectorId.value = taken
  },
  { immediate: true }
)

const connectorOptions = computed(() => [
  { label: "All connections", value: "" },
  ...(connectors.data.value?.data ?? []).map((connector) => ({
    label: connector.name,
    value: connector.id,
  })),
])
const rows = computed(() => documents.data.value?.data ?? [])
// Named and unnamed, apart: a draft is recognised by its first line and a
// named document by its name, so mixing them makes one list of two kinds of
// row that are read differently.
const named = computed(() => rows.value.filter((row) => row.title !== null))
const drafts = computed(() => rows.value.filter((row) => row.title === null))
const error = computed(() =>
  documents.isError.value
    ? messageOf(documents.error.value, "Could not read your queries")
    : ""
)

function pickConnector(value: unknown) {
  connectorId.value = value === "" || typeof value !== "string" ? null : value
}

/**
 * A new console, which is not yet a query anybody has.
 *
 * Nothing is written down: the library is what a person decided to keep, and
 * pressing this used to put an empty "Untitled" into it before a word had
 * been typed. The console keeps its text in its own tab until Remember (D65).
 */
function newDocument() {
  const chosen = connectorId.value
  if (chosen === null) return
  const draftId = crypto.randomUUID()
  writeDraft(draftId, emptyDraft())
  workspace.openQueryDraft({
    draftId,
    connectorId: chosen,
    connectorName: nameOf(chosen),
    title: null,
  })
}

/** What a connection is called, for the tab of a console with no name yet. */
function nameOf(id: string): string | null {
  return connectorNameOf(connectors.data.value, id)
}

function openDocument(row: {
  id: string
  title: string | null
  connector_id: string | null
  connector_label: string | null
}) {
  workspace.openQueryDocument({
    documentId: row.id,
    connectorId: row.connector_id ?? undefined,
    title: row.title,
    connectorName: row.connector_label,
  })
}

async function moveToTrash(documentId: string) {
  try {
    await trash.mutateAsync(documentId)
    toast.success("Moved to Trash")
  } catch (cause) {
    toast.error(messageOf(cause, "Could not delete this query"))
  }
}

async function bringBack(documentId: string) {
  try {
    await restore.mutateAsync(documentId)
    toast.success("Restored")
  } catch (cause) {
    toast.error(messageOf(cause, "Could not restore this query"))
  }
}

const runs = computed(() =>
  (history.data.value?.data ?? []).filter(
    (run) => connectorId.value === null || run.connector_id === connectorId.value
  )
)

function when(moment: string | null | undefined): string {
  return moment === null || moment === undefined
    ? ""
    : new Date(moment).toLocaleString()
}

/**
 * Put what a run executed back into a document of its own.
 *
 * A copy rather than a restoration: the run is immutable and stays exactly as
 * it was, and what comes back is a new console holding the same text (D63).
 */
async function openAsQuery(run: { id: string; connector_id: string | null }) {
  const connector = run.connector_id
  if (connector === null) {
    toast.info("The connection this ran against is no longer available")
    return
  }
  try {
    const text = await runText.mutateAsync(run.id)
    // A console holding what it ran, and not a second copy in the library:
    // the run is already the record of what was executed (D63).
    const draftId = crypto.randomUUID()
    writeDraft(draftId, { ...emptyDraft(), body: text.text })
    workspace.openQueryDraft({
      draftId,
      connectorId: connector,
      connectorName: nameOf(connector),
      title: null,
    })
  } catch (cause) {
    toast.error(messageOf(cause, "Could not open this run as a query"))
  }
}

async function forget(runId: string) {
  try {
    await deleteRuns.mutateAsync({ kind: "selected", ids: [runId] })
  } catch (cause) {
    toast.error(messageOf(cause, "Could not delete this run"))
  }
}

async function forgetEverything() {
  const accepted = await confirm({
    title: "Delete all of your query history?",
    message: "What ran is not kept anywhere else afterwards.",
    confirmLabel: "Delete",
    danger: true,
  })
  if (!accepted) return
  try {
    await deleteRuns.mutateAsync({ kind: "all" })
    toast.success("History deleted")
  } catch (cause) {
    toast.error(messageOf(cause, "Could not delete your history"))
  }
}

async function deleteForGood(documentId: string) {
  const accepted = await confirm({
    title: "Delete this query for good?",
    message: "Its text cannot be recovered afterwards.",
    confirmLabel: "Delete",
    danger: true,
  })
  if (!accepted) return
  try {
    await purge.mutateAsync(documentId)
    toast.success("Deleted")
  } catch (cause) {
    toast.error(messageOf(cause, "Could not delete this query"))
  }
}
</script>

<template>
  <div class="queries-panel">
    <div class="queries-panel__bar">
      <AppIconButton
        :icon="appIcons.add"
        :tooltip="
          connectorId === null
            ? 'Choose a connection to write a query against'
            : 'New query'
        "
        :disable="connectorId === null"
        data-testid="new-query"
        @click="newDocument"
      />
      <AppSelect
        :model-value="connectorId ?? ''"
        :options="connectorOptions"
        :loading="connectors.isLoading.value"
        compact
        class="queries-panel__connector"
        data-testid="queries-connector"
        @update:model-value="pickConnector"
      />
      <PanelCommands :panel-id="panelId" />
    </div>

    <!-- Three places, one of which is always the one you are in. As two
         toggles they overlapped: Trash did nothing while History was showing,
         and had to be greyed out to say so. -->
    <div
      class="queries-panel__places"
      role="tablist"
      data-testid="queries-places"
    >
      <button
        v-for="place in PLACES"
        :key="place.value"
        type="button"
        role="tab"
        class="queries-panel__place"
        :class="{ 'queries-panel__place--here': showing === place.value }"
        :aria-selected="showing === place.value"
        :data-testid="`queries-place-${place.value}`"
        @click="showing = place.value"
      >
        <q-icon
          :name="place.icon"
          size="14px"
        />
        {{ place.label }}
      </button>
    </div>

    <AppInput
      v-model="search"
      :placeholder="showing === 'history' ? 'Search what you ran' : 'Search queries'"
      compact
      clearable
      class="queries-panel__search"
      data-testid="queries-search"
    />
    <q-separator class="queries-panel__rule" />

    <div
      v-if="showing === 'history'"
      class="queries-panel__body"
      data-testid="queries-history-list"
    >
      <AppSpinner v-if="history.isPending.value" />
      <AppEmptyState
        v-else-if="runs.length === 0"
        :text="search ? 'No run matches that' : 'Nothing has been run yet'"
        data-testid="history-empty"
      />
      <template v-else>
        <div class="queries-panel__history-bar">
          <span class="queries-panel__heading">What you have run</span>
          <AppIconButton
            :icon="appIcons.deleteSweep"
            tooltip="Delete all of your history"
            data-testid="history-delete-all"
            @click="forgetEverything"
          />
        </div>
        <div
          v-for="run in runs"
          :key="run.id"
          class="queries-panel__row"
          :data-testid="`history-row-${run.id}`"
        >
          <button
            type="button"
            class="queries-panel__open"
            :data-testid="`history-restore-${run.id}`"
            @click="openAsQuery(run)"
          >
            <span class="queries-panel__title">{{ run.preview || "(empty)" }}</span>
            <span class="queries-panel__meta">
              {{ run.status }} · {{ when(run.created_at) }}
              <template v-if="run.duration_ms !== null">
                · {{ run.duration_ms }} ms
              </template>
              <!-- Which document this was run from, when it still has a name.
                   Without it the two lists read as the same list twice. -->
              <template v-if="run.document_title">
                · from {{ run.document_title }}
              </template>
            </span>
          </button>
          <AppIconButton
            :icon="appIcons.delete"
            tooltip="Delete this run"
            :data-testid="`history-delete-${run.id}`"
            @click="forget(run.id)"
          />
        </div>
      </template>
    </div>

    <div
      v-else
      class="queries-panel__body"
    >
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="queries-error"
      >
        {{ error }}
      </AppBanner>
      <AppSpinner v-else-if="documents.isPending.value" />
      <AppEmptyState
        v-else-if="rows.length === 0"
        :text="
          trashed
            ? 'Nothing in Trash'
            : search
              ? 'No query matches that'
              : 'No queries yet'
        "
        data-testid="queries-empty"
      />
      <template v-else>
        <section
          v-for="group in [
            { key: 'named', title: 'Named', rows: named },
            { key: 'drafts', title: 'Drafts', rows: drafts },
          ]"
          v-show="group.rows.length > 0"
          :key="group.key"
          class="queries-panel__group"
        >
          <h3 class="queries-panel__heading">
            {{ group.title }}
          </h3>
          <div
            v-for="row in group.rows"
            :key="row.id"
            class="queries-panel__row"
            :data-testid="`query-row-${row.id}`"
          >
            <button
              type="button"
              class="queries-panel__open"
              :data-testid="`open-query-${row.id}`"
              @click="openDocument(row)"
            >
              <span class="queries-panel__title">{{ row.title ?? "Untitled query" }}</span>
              <span class="queries-panel__meta">
                {{ row.connector_label ?? "Connection unavailable" }}
                <template v-if="row.preview"> · {{ row.preview }}</template>
              </span>
            </button>
            <AppIconButton
              v-if="trashed"
              :icon="appIcons.restoreFromTrash"
              tooltip="Restore"
              :data-testid="`restore-query-${row.id}`"
              @click="bringBack(row.id)"
            />
            <AppIconButton
              v-if="trashed"
              :icon="appIcons.deleteForever"
              tooltip="Delete for good"
              :data-testid="`purge-query-${row.id}`"
              @click="deleteForGood(row.id)"
            />
            <AppIconButton
              v-else
              :icon="appIcons.delete"
              tooltip="Move to Trash"
              :data-testid="`trash-query-${row.id}`"
              @click="moveToTrash(row.id)"
            />
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.queries-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.queries-panel__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  padding: var(--dp-space-half) var(--dp-space-1) 0;
}
.queries-panel__connector {
  flex: 1;
  min-width: 0;
}
.queries-panel__places {
  flex: none;
  display: flex;
  gap: var(--dp-space-half);
  padding: var(--dp-space-1) var(--dp-space-2) 0;
}
.queries-panel__place {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--dp-space-1);
  padding: var(--dp-space-1) var(--dp-space-2);
  border: none;
  border-radius: var(--dp-radius-control);
  background: none;
  color: var(--dp-text-muted);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.queries-panel__place:hover {
  background: var(--dp-hover);
}
/* The one you are in, said by weight and ground rather than by a tick: three
   of these sit in a column a fifth of the screen wide. */
.queries-panel__place--here {
  background: var(--dp-surface-raised);
  color: var(--dp-text-strong);
  font-weight: 600;
}
.queries-panel__search {
  flex: none;
  padding: 0 var(--dp-space-2);
}
.queries-panel__rule {
  flex: none;
  margin: var(--dp-space-1) var(--dp-space-2);
}
.queries-panel__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 var(--dp-space-1) var(--dp-space-2);
}
.queries-panel__history-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-inline-end: var(--dp-space-1);
}
.queries-panel__heading {
  margin: var(--dp-space-2) var(--dp-space-2) var(--dp-space-half);
  color: var(--dp-text-muted);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.queries-panel__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
  padding-inline-end: var(--dp-space-half);
  border-radius: var(--dp-radius-control);
}
.queries-panel__row:hover {
  background: var(--dp-hover);
}
.queries-panel__open {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: var(--dp-space-1) var(--dp-space-2);
  border: none;
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}
.queries-panel__title {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.queries-panel__meta {
  overflow: hidden;
  color: var(--dp-text-muted);
  font-size: 11px;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
