<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue"
import type { ComponentPublicInstance } from "vue"

import type { DocumentItem, DocumentsRequest } from "@/client"
import CodeEditor from "@/features/content/CodeEditor.vue"
import JsonTreeNode from "@/features/content/JsonTreeNode.vue"
import { useChangeDocument, useDeleteDocuments, useDocuments, useInsertDocument } from "@/features/content/api"
import {
  DOCUMENT_PAGE_SIZES,
  isDocumentPageSize,
  loadDocumentPageSize,
  saveDocumentPageSize,
} from "@/features/content/documentsPageSize"
import { cloneText, documentId } from "@/features/content/jsonTree"
import { loadGridState } from "@/features/grid/persist"
import DictateButton from "@/features/speech/DictateButton.vue"
import { useDictation } from "@/features/speech/dictation"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useClosable } from "@/features/workspace/closable"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { copyText } from "@/shared/clipboard"
import { errorKindOf, messageOf, statusOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppBanner,
  AppButton,
  AppIconButton,
  AppSelect,
  AppSpinner,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"

/**
 * A collection's documents whole, a page at a time, each edited as JSON (D295).
 *
 * The page is the grid's own query: the filters and order the table over the
 * same collection was left with, read when this opens and on every reload, so
 * switching between the two shows the same documents. An edit is sent as the
 * whole text and written by the server field by field, so a value nobody
 * touched keeps its type. A new document, a clone included, is written in the
 * same editor above the list and added as written (D459).
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
}>()

const toast = useToast()
const workspace = useWorkspaceActions()
const confirm = useConfirm()
const connectorId = computed(() => props.connectorId)

function gridQuery(): Pick<DocumentsRequest, "filters" | "sort"> {
  const stored = loadGridState(props.connectorId, props.nodeId)
  return { filters: stored?.filters ?? [], sort: stored?.sort ?? [] }
}

const query = ref(gridQuery())
const offset = ref(0)
const pageSize = ref(loadDocumentPageSize())
const pageSizeOptions = DOCUMENT_PAGE_SIZES.map((size) => ({ label: String(size), value: size }))
const request = computed<DocumentsRequest>(() => ({
  node_id: props.nodeId,
  limit: pageSize.value,
  offset: offset.value,
  filters: query.value.filters,
  sort: query.value.sort,
}))
const documents = useDocuments(connectorId, request)
const changeDocument = useChangeDocument(connectorId)
const insertDocument = useInsertDocument(connectorId)
const deleteDocuments = useDeleteDocuments(connectorId)
const errorKind = computed(() => errorKindOf(documents.error.value))
const error = computed(() =>
  documents.isError.value ? messageOf(documents.error.value, t("content.documents.could_not_open")) : ""
)
const page = computed(() => documents.data.value ?? null)
const fromTable = computed(() => (query.value.filters?.length ?? 0) + (query.value.sort?.length ?? 0) > 0)
const range = computed(() => {
  const count = page.value?.items.length ?? 0
  return count === 0 ? "" : t("content.documents.range", { from: offset.value + 1, to: offset.value + count })
})

// One document is edited at a time, by its handle.
const editing = ref<string | null>(null)
const draft = ref("")
const original = ref("")
const saveError = ref("")
const conflict = ref(false)
const dirty = computed(() => editing.value !== null && draft.value !== original.value)

// A document being written anew, in its own editor above the list.
const adding = ref(false)
const addingTitle = ref("")
const addDraft = ref("")
const addOriginal = ref("")
const addError = ref("")
const addDirty = computed(() => adding.value && addDraft.value !== addOriginal.value)

/** The editor of the document being edited, which is where words spoken go (D138). */
const documentEditor = ref<InstanceType<typeof CodeEditor> | null>(null)
/** A string ref inside the document list would resolve to an array (Vue's v-for ref rule). */
function setDocumentEditor(editor: Element | ComponentPublicInstance | null) {
  documentEditor.value = editor as InstanceType<typeof CodeEditor> | null
}
const dictation = useDictation((heard) => documentEditor.value?.writeSpeech(heard))
// A document nobody is editing is not dictated into.
watch(editing, () => dictation.stop())
onBeforeUnmount(() => dictation.stop())

function canEdit(item: DocumentItem): boolean {
  return page.value?.change_supported === true && !item.truncated && item.row_handle != null
}

function canDelete(item: DocumentItem): boolean {
  return page.value?.change_supported === true && item.row_handle != null
}

/** Written from the tree, so a document too large to draw is not cloned. */
function canClone(item: DocumentItem): boolean {
  return page.value?.insert_supported === true && item.value != null
}

async function leaveEdit(): Promise<boolean> {
  if (!dirty.value && !addDirty.value) return true
  return await confirm({
    title: t("content.documents.discard_title"),
    message: t("content.documents.discard_message"),
    confirmLabel: t("content.documents.discard_confirm"),
    danger: true,
  })
}

async function startEdit(item: DocumentItem) {
  if (item.row_handle == null || !(await leaveEdit())) return
  stopAdd()
  editing.value = item.row_handle
  draft.value = item.text
  original.value = item.text
  saveError.value = ""
  conflict.value = false
}

function stopEdit() {
  editing.value = null
  saveError.value = ""
  conflict.value = false
}

async function save(item: DocumentItem) {
  if (item.row_handle == null) return
  saveError.value = ""
  conflict.value = false
  try {
    const answer = await changeDocument.mutateAsync({
      node_id: props.nodeId,
      row_handle: item.row_handle,
      change: { kind: "document", text: draft.value },
    })
    toast.success(
      answer.changed === 0
        ? t("content.documents.unchanged")
        : t("content.documents.saved", { n: answer.changed }, answer.changed)
    )
    stopEdit()
  } catch (cause) {
    saveError.value = messageOf(cause, t("content.documents.could_not_save"))
    conflict.value = statusOf(cause) === 409
  }
}

async function startAdd(from?: DocumentItem) {
  if (!(await leaveEdit())) return
  stopEdit()
  const text = from?.value == null ? "{\n  \n}" : cloneText(from.value)
  addingTitle.value =
    from?.value == null
      ? t("content.documents.new_title")
      : t("content.documents.clone_title", { id: documentId(from.value) })
  addDraft.value = text
  addOriginal.value = text
  addError.value = ""
  adding.value = true
}

function stopAdd() {
  adding.value = false
  addError.value = ""
}

async function add() {
  addError.value = ""
  try {
    await insertDocument.mutateAsync({ node_id: props.nodeId, text: addDraft.value })
    toast.success(t("content.documents.inserted"))
    stopAdd()
  } catch (cause) {
    addError.value = messageOf(cause, t("content.documents.could_not_insert"))
  }
}

async function remove(item: DocumentItem) {
  if (item.row_handle == null) return
  const confirmed = await confirm({
    title: t("content.documents.delete_title"),
    message: t("content.documents.delete_message", { id: documentId(item.value) }),
    confirmLabel: t("content.documents.delete_confirm"),
    danger: true,
  })
  if (!confirmed) return
  try {
    await deleteDocuments.mutateAsync({ node_id: props.nodeId, row_handles: [item.row_handle] })
    if (editing.value === item.row_handle) stopEdit()
    toast.success(t("content.documents.deleted"))
  } catch (cause) {
    toast.error(messageOf(cause, t("content.documents.could_not_delete")))
  }
}

async function copy(item: DocumentItem) {
  try {
    await copyText(item.text)
    toast.success(t("content.documents.copied"))
  } catch (cause) {
    toast.error(messageOf(cause, t("content.documents.could_not_copy")))
  }
}

async function turn(step: number) {
  if (!(await leaveEdit())) return
  stopEdit()
  stopAdd()
  offset.value = Math.max(0, offset.value + step * pageSize.value)
}

async function choosePageSize(value: unknown) {
  if (!isDocumentPageSize(value) || value === pageSize.value || !(await leaveEdit())) return
  stopEdit()
  stopAdd()
  pageSize.value = value
  saveDocumentPageSize(value)
  offset.value = 0
}

async function reload() {
  if (!(await leaveEdit())) return
  stopEdit()
  stopAdd()
  query.value = gridQuery()
  await documents.refetch()
}

/** The collection's options, validator and indexes, which no other tab of it opens. */
function showDefinition() {
  workspace.openRepresentation({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    representations: [{ kind: "tree", title: t("content.tree.kind") }],
    describable: true,
  })
}

useReloadable(() => props.panelId, reload)
useClosable(props.panelId, leaveEdit)
</script>

<template>
  <div class="documents-panel">
    <div class="documents-panel__head">
      <span class="documents-panel__details">
        {{ range }}
        <template v-if="fromTable"> · {{ t("content.documents.from_table") }}</template>
      </span>
      <div class="documents-panel__commands">
        <AppIconButton
          v-if="page?.insert_supported === true"
          :icon="appIcons.add"
          :tooltip="t('content.documents.new')"
          data-testid="documents-new"
          @click="startAdd()"
        />
        <AppIconButton
          :icon="appIcons.accountTree"
          :tooltip="t('content.documents.definition')"
          data-testid="documents-definition"
          @click="showDefinition"
        />
        <AppSelect
          :model-value="pageSize"
          :options="pageSizeOptions"
          :label="t('content.documents.per_page')"
          compact
          class="documents-panel__page-size"
          data-testid="documents-page-size"
          @update:model-value="choosePageSize"
        />
        <AppIconButton
          :icon="appIcons.chevronLeft"
          :tooltip="t('content.documents.previous')"
          :disable="offset === 0"
          data-testid="documents-previous"
          @click="turn(-1)"
        />
        <AppIconButton
          :icon="appIcons.chevronRight"
          :tooltip="t('content.documents.next')"
          :disable="page?.has_more !== true"
          data-testid="documents-next"
          @click="turn(1)"
        />
        <PanelCommands
          :panel-id="panelId"
          :reveal="{ connectorId, nodeId, label: title }"
        />
      </div>
    </div>

    <SourceErrorBanner
      v-if="error"
      :connector-id="connectorId"
      :error-kind="errorKind"
      data-testid="documents-error"
    >
      {{ error }}
    </SourceErrorBanner>
    <AppSpinner v-else-if="documents.isPending.value" />
    <div
      v-else-if="page !== null"
      class="documents-panel__list"
    >
      <section
        v-if="adding"
        class="documents-panel__document"
        data-testid="document-new"
      >
        <div class="documents-panel__document-head">
          <span class="documents-panel__id">{{ addingTitle }}</span>
        </div>
        <AppBanner
          v-if="addError"
          tone="error"
          data-testid="document-new-error"
        >
          {{ addError }}
        </AppBanner>
        <div class="documents-panel__editor">
          <CodeEditor
            v-model="addDraft"
            filename="document.json"
            validation="json"
          />
        </div>
        <div class="documents-panel__edit-actions">
          <AppButton
            variant="quiet"
            size="sm"
            :label="t('content.documents.cancel')"
            data-testid="document-new-cancel"
            @click="stopAdd"
          />
          <AppButton
            variant="primary"
            size="sm"
            :icon="appIcons.add"
            :label="t('content.documents.insert')"
            :loading="insertDocument.isPending.value"
            data-testid="document-new-save"
            @click="add"
          />
        </div>
      </section>
      <div
        v-if="page.items.length === 0"
        class="documents-panel__empty"
        data-testid="documents-empty"
      >
        {{ t("content.documents.none") }}
      </div>
      <section
        v-for="(item, index) in page.items"
        :key="item.row_handle ?? `${offset + index}`"
        class="documents-panel__document"
        data-testid="document"
      >
        <div class="documents-panel__document-head">
          <span class="documents-panel__number">{{ offset + index + 1 }}</span>
          <span class="documents-panel__id">{{ documentId(item.value) }}</span>
          <div class="documents-panel__document-actions">
            <AppIconButton
              :icon="appIcons.copy"
              :tooltip="t('content.documents.copy')"
              data-testid="document-copy"
              @click="copy(item)"
            />
            <AppIconButton
              v-if="canClone(item)"
              :icon="appIcons.clone"
              :tooltip="t('content.documents.clone')"
              data-testid="document-clone"
              @click="startAdd(item)"
            />
            <AppIconButton
              v-if="canEdit(item) && editing !== item.row_handle"
              :icon="appIcons.edit"
              :tooltip="t('content.documents.edit')"
              data-testid="document-edit"
              @click="startEdit(item)"
            />
            <AppIconButton
              v-if="canDelete(item)"
              :icon="appIcons.delete"
              variant="danger-quiet"
              :tooltip="t('content.documents.delete')"
              :disable="deleteDocuments.isPending.value"
              data-testid="document-delete"
              @click="remove(item)"
            />
          </div>
        </div>

        <template v-if="editing !== null && editing === item.row_handle">
          <AppBanner
            v-if="saveError"
            tone="error"
            data-testid="document-save-error"
          >
            {{ saveError }}
            <AppButton
              v-if="conflict"
              variant="quiet"
              size="sm"
              :label="t('content.documents.reload')"
              data-testid="document-reload"
              @click="reload"
            />
          </AppBanner>
          <div class="documents-panel__editor">
            <CodeEditor
              :ref="setDocumentEditor"
              v-model="draft"
              filename="document.json"
              validation="json"
            />
          </div>
          <div class="documents-panel__edit-actions">
            <DictateButton
              :dictation="dictation"
              testid="document-dictate"
              @start="documentEditor?.startSpeech()"
            />
            <AppButton
              variant="quiet"
              size="sm"
              :label="t('content.documents.cancel')"
              data-testid="document-cancel"
              @click="stopEdit"
            />
            <AppButton
              variant="primary"
              size="sm"
              :icon="appIcons.save"
              :label="t('content.documents.save')"
              :loading="changeDocument.isPending.value"
              :disable="!dirty"
              data-testid="document-save"
              @click="save(item)"
            />
          </div>
        </template>
        <template v-else>
          <AppBanner
            v-if="item.truncated"
            tone="warning"
          >
            {{ t("content.documents.truncated") }}
          </AppBanner>
          <JsonTreeNode
            v-if="item.value"
            :value="item.value"
            :open-levels="0"
            root
          />
          <pre
            v-else
            class="documents-panel__text"
          >{{ item.text }}</pre>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.documents-panel {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
}
.documents-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
}
.documents-panel__details,
.documents-panel__number,
.documents-panel__empty {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
}
.documents-panel__commands,
.documents-panel__document-actions,
.documents-panel__edit-actions {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
}
.documents-panel__edit-actions {
  justify-content: flex-end;
}
.documents-panel__list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--dp-space-2);
  min-height: 0;
  overflow: auto;
  padding: var(--dp-space-2);
}
.documents-panel__document {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  padding: var(--dp-space-2);
  border: 1px solid var(--dp-border-faint);
  border-radius: var(--dp-radius-panel);
}
.documents-panel__document-head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}
.documents-panel__id {
  flex: 1;
  overflow: hidden;
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.documents-panel__page-size {
  width: max-content;
  min-width: 140px;
  flex: none;
}
.documents-panel__editor {
  height: 320px;
}
.documents-panel__text {
  margin: 0;
  overflow: auto;
  font-family: var(--dp-font-mono);
  font-size: var(--dp-font-size-xs);
}
</style>
