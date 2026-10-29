<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import { connectorNameOf, useConnectors } from "@/features/connectors/api"
import {
  useDeleteQueryDocument,
  useQueryDocuments,
} from "@/features/queries/api"
import { statusWord } from "@/features/queries/console"
import { clearShadow, emptyDraft, writeDraft } from "@/features/queries/draft"
import {
  useDeleteRuns,
  useRunHistory,
  useRunText,
} from "@/features/queries/runs"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { formatDateTime } from "@/shared/i18n/format"
import {
  AppBanner,
  AppEmptyState,
  AppIconButton,
  AppInput,
  AppSelect,
  AppSpinner,
  AppTabs,
  AppToolbarRule,
  useConfirm,
  useToast,
} from "@/shared/ui"

import { useQueriesLibrary } from "./library"
import type { LibraryPlace } from "./library"
import { newId } from "@/shared/ids"

/**
 * The library of query documents (D65), a tool of the panel at the foot of
 * the screen (D143).
 *
 * Not a node of any catalog: a query belongs to a person, not to a database,
 * and one of them may outlive the connection it was written against. The
 * panel is wide and low, so what chooses what is listed is one row.
 */

/**
 * The two places this panel holds, and what each of them answers.
 *
 * Favorites are the documents somebody kept; History is what actually ran.
 * They read alike — both are lists of SQL — so each row says which kind of
 * thing it is: a document by its name and its connection, a run by what it
 * did, when, and which document it was run from.
 */
const places = computed<{ value: LibraryPlace; label: string; icon: string }[]>(() => [
  { value: "favorites", label: t("queries.library.favorites"), icon: appIcons.star },
  { value: "history", label: t("queries.library.history"), icon: appIcons.history },
])

const workspace = useWorkspaceActions()
const toast = useToast()
const confirm = useConfirm()
const connectors = useConnectors()

const { place: showing, connectorId } = useQueriesLibrary()
const search = ref("")

function show(value: string) {
  if (value === "favorites" || value === "history") showing.value = value
}

const filters = computed(() => ({
  connectorId: connectorId.value,
  search: search.value.trim(),
}))
const documents = useQueryDocuments(filters)
const history = useRunHistory(
  () => null,
  () => search.value.trim()
)
const runText = useRunText()
const deleteRuns = useDeleteRuns()
const deleteDocument = useDeleteQueryDocument()

const connectorOptions = computed(() => [
  { label: t("queries.library.all_connections"), value: "" },
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
    ? messageOf(documents.error.value, t("queries.library.read_failed"))
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
  const draftId = newId()
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

const runs = computed(() =>
  (history.data.value?.data ?? []).filter(
    (run) => connectorId.value === null || run.connector_id === connectorId.value
  )
)

function when(moment: string | null | undefined): string {
  return moment === null || moment === undefined
    ? ""
    : formatDateTime(moment)
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
    toast.info(t("queries.library.connection_gone"))
    return
  }
  try {
    const text = await runText.mutateAsync(run.id)
    // A console holding what it ran, and not a second copy in the library:
    // the run is already the record of what was executed (D63).
    const draftId = newId()
    writeDraft(draftId, { ...emptyDraft(), body: text.text })
    workspace.openQueryDraft({
      draftId,
      connectorId: connector,
      connectorName: nameOf(connector),
      title: null,
    })
  } catch (cause) {
    toast.error(messageOf(cause, t("queries.library.open_run_failed")))
  }
}

async function forget(runId: string) {
  const accepted = await confirm({
    title: t("queries.library.delete_run_title"),
    message: t("queries.library.delete_run_message"),
    confirmLabel: t("queries.common.delete"),
    danger: true,
  })
  if (!accepted) return
  try {
    await deleteRuns.mutateAsync({ kind: "selected", ids: [runId] })
  } catch (cause) {
    toast.error(messageOf(cause, t("queries.library.delete_run_failed")))
  }
}

async function forgetEverything() {
  const accepted = await confirm({
    title: t("queries.library.delete_all_title"),
    message: t("queries.library.delete_run_message"),
    confirmLabel: t("queries.common.delete"),
    danger: true,
  })
  if (!accepted) return
  try {
    await deleteRuns.mutateAsync({ kind: "all" })
    toast.success(t("queries.library.history_deleted"))
  } catch (cause) {
    toast.error(messageOf(cause, t("queries.library.delete_history_failed")))
  }
}

async function deleteQuery(documentId: string) {
  const accepted = await confirm({
    title: t("queries.library.delete_query_title"),
    message: t("queries.library.delete_query_message"),
    confirmLabel: t("queries.common.delete"),
    danger: true,
  })
  if (!accepted) return
  try {
    await deleteDocument.mutateAsync(documentId)
    clearShadow(documentId)
    workspace.closeQueryDocument(documentId)
    toast.success(t("queries.library.deleted"))
  } catch (cause) {
    toast.error(messageOf(cause, t("queries.library.delete_query_failed")))
  }
}
</script>

<template>
  <div class="queries-tool">
    <div class="queries-tool__bar">
      <!-- Saved documents and execution history answer different questions. -->
      <AppTabs
        :model-value="showing"
        :options="places"
        data-testid="queries-places"
        @update:model-value="show"
      />
      <AppToolbarRule />
      <AppIconButton
        :icon="appIcons.add"
        :tooltip="
          connectorId === null
            ? t('queries.library.choose_connection')
            : t('queries.library.new_query')
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
        class="queries-tool__connector"
        data-testid="queries-connector"
        @update:model-value="pickConnector"
      />
      <AppInput
        v-model="search"
        :placeholder="
          showing === 'history'
            ? t('queries.library.search_history')
            : t('queries.library.search_favorites')
        "
        compact
        clearable
        class="queries-tool__search"
        data-testid="queries-search"
      />
    </div>

    <div
      v-if="showing === 'history'"
      class="queries-tool__body"
      data-testid="queries-history-list"
    >
      <AppSpinner v-if="history.isPending.value" />
      <AppEmptyState
        v-else-if="runs.length === 0"
        :text="search ? t('queries.library.no_run_matches') : t('queries.library.nothing_run')"
        inset
        data-testid="history-empty"
      />
      <template v-else>
        <div class="queries-tool__history-bar">
          <span class="queries-tool__heading dp-overline">{{ t("queries.library.what_you_ran") }}</span>
          <AppIconButton
            :icon="appIcons.deleteSweep"
            :tooltip="t('queries.library.delete_all_history')"
            variant="danger-quiet"
            data-testid="history-delete-all"
            @click="forgetEverything"
          />
        </div>
        <div
          v-for="run in runs"
          :key="run.id"
          class="queries-tool__row"
          :data-testid="`history-row-${run.id}`"
        >
          <button
            type="button"
            class="queries-tool__open"
            :data-testid="`history-restore-${run.id}`"
            @click="openAsQuery(run)"
          >
            <span class="queries-tool__title">{{ run.preview || t("queries.library.empty_preview") }}</span>
            <span class="queries-tool__meta">
              {{ statusWord(run.status) }} · {{ when(run.created_at) }}
              <template v-if="run.duration_ms !== null && run.duration_ms !== undefined">
                · {{ t("queries.duration.ms", { n: run.duration_ms }) }}
              </template>
              <!-- Which document this was run from, when it still has a name.
                   Without it the two lists read as the same list twice. -->
              <template v-if="run.document_title">
                · {{ t("queries.library.from", { title: run.document_title }) }}
              </template>
            </span>
          </button>
          <AppIconButton
            :icon="appIcons.delete"
            :tooltip="t('queries.library.delete_run')"
            variant="danger-quiet"
            :data-testid="`history-delete-${run.id}`"
            @click="forget(run.id)"
          />
        </div>
      </template>
    </div>

    <div
      v-else
      class="queries-tool__body"
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
        :text="search ? t('queries.library.no_query_matches') : t('queries.library.no_favorites')"
        inset
        data-testid="queries-empty"
      />
      <template v-else>
        <section
          v-for="group in [
            { key: 'named', title: t('queries.library.named'), rows: named },
            { key: 'drafts', title: t('queries.library.drafts'), rows: drafts },
          ]"
          v-show="group.rows.length > 0"
          :key="group.key"
          class="queries-tool__group"
        >
          <h3 class="queries-tool__heading dp-overline">
            {{ group.title }}
          </h3>
          <div
            v-for="row in group.rows"
            :key="row.id"
            class="queries-tool__row"
            :data-testid="`query-row-${row.id}`"
          >
            <button
              type="button"
              class="queries-tool__open"
              :data-testid="`open-query-${row.id}`"
              @click="openDocument(row)"
            >
              <span class="queries-tool__title">{{ row.title ?? t("queries.common.untitled") }}</span>
              <span class="queries-tool__meta">
                {{ row.connector_label ?? t("queries.common.connection_unavailable") }}
                <template v-if="row.preview"> · {{ row.preview }}</template>
              </span>
            </button>
            <AppIconButton
              :icon="appIcons.delete"
              :tooltip="t('queries.library.delete_query')"
              variant="danger-quiet"
              :data-testid="`delete-query-${row.id}`"
              @click="deleteQuery(row.id)"
            />
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.queries-tool {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
/* One row: the panel is wide and low, and every row above the list is taken
   from the few the list has. */
.queries-tool__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: 0 var(--dp-space-2) var(--dp-space-2) 0;
  border-bottom: 1px solid var(--dp-border);
}
.queries-tool__connector {
  flex: 0 1 240px;
  min-width: 0;
}
.queries-tool__search {
  flex: 0 1 320px;
  min-width: 0;
}
.queries-tool__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-inline-end: var(--dp-space-2);
}
.queries-tool__history-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-inline-end: var(--dp-space-1);
}
.queries-tool__heading {
  margin: var(--dp-space-2) var(--dp-space-2) var(--dp-space-half);
}
.queries-tool__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
  padding-inline-end: var(--dp-space-half);
  border-radius: var(--dp-radius-control);
}
.queries-tool__row:hover {
  background: var(--dp-hover);
}
.queries-tool__open {
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
.queries-tool__title {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.queries-tool__meta {
  overflow: hidden;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
