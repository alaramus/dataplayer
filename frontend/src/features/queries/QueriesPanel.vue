<script setup lang="ts">
import { computed, ref } from "vue"

import { useConnectors } from "@/features/connectors/api"
import {
  useCreateQueryDocument,
  usePurgeQueryDocument,
  useQueryDocuments,
  useRestoreQueryDocument,
  useTrashQueryDocument,
} from "@/features/queries/api"
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

const props = defineProps<{ panelId: string }>()

const workspace = useWorkspaceActions()
const toast = useToast()
const confirm = useConfirm()
const connectors = useConnectors()

const connectorId = ref<string | null>(null)
const search = ref("")
const trashed = ref(false)

const filters = computed(() => ({
  connectorId: connectorId.value,
  search: search.value.trim(),
  trashed: trashed.value,
}))
const documents = useQueryDocuments(filters)
const create = useCreateQueryDocument()
const trash = useTrashQueryDocument()
const restore = useRestoreQueryDocument()
const purge = usePurgeQueryDocument()

useReloadable(props.panelId, async () => {
  await documents.refetch()
})

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

async function newDocument() {
  const chosen = connectorId.value
  if (chosen === null) return
  try {
    const document = await create.mutateAsync({ connector_id: chosen })
    workspace.openQueryDocument({
      documentId: document.id,
      title: document.title,
      connectorName: document.connector_label,
    })
  } catch (cause) {
    toast.error(messageOf(cause, "Could not open a new query"))
  }
}

function openDocument(row: { id: string; title: string | null; connector_label: string | null }) {
  workspace.openQueryDocument({
    documentId: row.id,
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
        icon="add"
        :tooltip="
          connectorId === null
            ? 'Choose a connection to write a query against'
            : 'New query'
        "
        :disable="connectorId === null || create.isPending.value"
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
      <AppIconButton
        icon="delete"
        :tooltip="trashed ? 'Back to your queries' : 'Trash'"
        :aria-pressed="trashed"
        data-testid="queries-trash"
        @click="trashed = !trashed"
      />
    </div>

    <AppInput
      v-model="search"
      placeholder="Search queries"
      compact
      clearable
      class="queries-panel__search"
      data-testid="queries-search"
    />
    <q-separator class="queries-panel__rule" />

    <div class="queries-panel__body">
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
              icon="restore_from_trash"
              tooltip="Restore"
              :data-testid="`restore-query-${row.id}`"
              @click="bringBack(row.id)"
            />
            <AppIconButton
              v-if="trashed"
              icon="delete_forever"
              tooltip="Delete for good"
              :data-testid="`purge-query-${row.id}`"
              @click="deleteForGood(row.id)"
            />
            <AppIconButton
              v-else
              icon="delete"
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
  gap: 4px;
  padding: 2px 4px 0;
}
.queries-panel__connector {
  flex: 1;
  min-width: 0;
}
.queries-panel__search {
  flex: none;
  padding: 0 8px;
}
.queries-panel__rule {
  flex: none;
  margin: 4px 8px;
}
.queries-panel__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 4px 8px;
}
.queries-panel__heading {
  margin: 8px 8px 2px;
  color: var(--dp-text-muted);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.queries-panel__row {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-inline-end: 2px;
  border-radius: 4px;
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
  padding: 5px 8px;
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
