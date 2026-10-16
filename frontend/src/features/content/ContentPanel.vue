<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref, watch } from "vue"

import type { EditorContent, EditorContentRequest } from "@/client"
import CodeEditor from "@/features/content/CodeEditor.vue"
import { useEditorContent, useUpdateContent } from "@/features/content/api"
import ReadAloudButton from "@/features/speech/ReadAloudButton.vue"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { useClosable } from "@/features/workspace/closable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { errorKindOf, messageOf, statusOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppBanner, AppButton, AppSpinner, useConfirm, useToast } from "@/shared/ui"

const props = defineProps<{
  panelId: string
  connectorId: string
  nodeId: string
  title: string
  connectorName: string
  adapterType: string
  representation: "text" | "json" | "jsonl"
  tableTitle?: string
}>()

const connectorId = computed(() => props.connectorId)
const request = computed<EditorContentRequest>(() => ({ node_id: props.nodeId }))
const editor = useEditorContent(connectorId, request)
const errorKind = computed(() => errorKindOf(editor.error.value))
const updateContent = useUpdateContent(connectorId)
const workspace = useWorkspaceActions()
const toast = useToast()
const confirm = useConfirm()

const draft = ref("")
const baseline = ref("")
const loadedVersion = ref<string | null>(null)
const saveError = ref("")
const saveConflict = ref(false)

const dirty = computed(() => draft.value !== baseline.value)
useClosable(props.panelId, async () => {
  if (updateContent.isPending.value) {
    toast.info(t("content.editor.wait_for_save"))
    return false
  }
  return !dirty.value || await confirm({
    title: t("content.editor.discard_title"),
    message: t("content.editor.discard_message", { name: props.title }),
    confirmLabel: t("content.editor.discard_confirm"),
    danger: true,
  })
})
const writable = computed(() => editor.data.value?.writable === true)
const canSave = computed(() => writable.value && loadedVersion.value !== null && dirty.value)
const error = computed(() =>
  editor.isError.value ? messageOf(editor.error.value, t("content.common.could_not_open_file")) : ""
)
/* Said the way a media panel says "PNG · 68 B": a format's name, in capitals
   only where it is an acronym. "TEXT" above an editor read as the one
   overline among the panels' meta lines. */
const kindLabel = computed(() => {
  if (props.representation === "jsonl") return t("content.editor.json_lines")
  if (props.representation === "text") return t("content.editor.plain_text")
  return props.representation.toUpperCase()
})

function hydrate(value: EditorContent) {
  draft.value = value.text
  baseline.value = value.text
  loadedVersion.value = value.version ?? null
  saveError.value = ""
  saveConflict.value = false
}

async function reload() {
  const result = await editor.refetch()
  if (result.data) hydrate(result.data)
}

// Re-reading would discard an edit that only exists here, so an unsaved
// document is left alone and the reason is said rather than guessed at.
useReloadable(() => props.panelId, async () => {
  if (dirty.value) {
    toast.info(t("content.editor.unsaved_before_reload"))
    return
  }
  await reload()
})

async function save() {
  const version = loadedVersion.value
  if (!canSave.value || version === null) return
  saveError.value = ""
  saveConflict.value = false
  const saved = draft.value
  try {
    const result = await updateContent.mutateAsync({
      node_id: props.nodeId,
      text: saved,
      version,
    })
    baseline.value = saved
    loadedVersion.value = result.version
    toast.success(t("content.editor.saved", { name: props.title }))
  } catch (cause) {
    saveError.value = messageOf(cause, t("content.editor.could_not_save"))
    saveConflict.value = statusOf(cause) === 409
  }
}

function showTable() {
  workspace.openRows({
    connectorId: props.connectorId,
    nodeId: props.nodeId,
    title: props.title,
    connectorName: props.connectorName,
    adapterType: props.adapterType,
    // A file has no structure to describe: its columns exist only in the
    // projection this tab is asking for.
    describable: false,
    // Said so the tab is drawn as the grid the catalog drew, rather than as
    // the folder its source is. The title is the source's own: this panel was
    // given it because the node declared a table.
    representations: props.tableTitle
      ? [{ kind: "table", title: props.tableTitle }]
      : undefined,
  })
}

watch(
  () => editor.data.value,
  (value) => {
    // Only the first answer fills the editor: a later refetch must not take
    // back what is being typed.
    if (value && loadedVersion.value === null && !dirty.value) hydrate(value)
  },
  { immediate: true }
)
</script>

<template>
  <div class="content-panel">
    <div class="content-panel__head">
      <span class="content-panel__kind">{{ kindLabel }}</span>
      <div class="content-panel__actions">
        <ReadAloudButton
          v-if="editor.data.value"
          :text="draft"
          :listen-label="t('content.editor.listen')"
          testid="content-listen"
        />
        <span
          v-if="dirty"
          class="content-panel__dirty"
          data-testid="content-dirty"
        >
          {{ t("content.editor.unsaved") }}
        </span>
        <AppButton
          v-if="writable"
          variant="primary"
          size="sm"
          :icon="appIcons.save"
          :label="t('content.editor.save')"
          :loading="updateContent.isPending.value"
          :disable="!canSave"
          data-testid="content-save"
          @click="save"
        />
        <AppButton
          v-if="tableTitle"
          variant="quiet"
          size="sm"
          :icon="appIcons.gridOn"
          :label="tableTitle"
          data-testid="content-view-table"
          @click="showTable"
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
      data-testid="content-error"
    >
      {{ error }}
    </SourceErrorBanner>

    <AppSpinner v-else-if="editor.isPending.value" />

    <div
      v-else-if="editor.data.value"
      class="content-panel__editor"
    >
      <AppBanner
        v-if="editor.data.value.reason"
        tone="warning"
        class="content-panel__notice"
        data-testid="content-notice"
      >
        {{ editor.data.value.reason }}
      </AppBanner>
      <AppBanner
        v-if="saveError"
        tone="error"
        class="content-panel__notice"
        data-testid="content-save-error"
      >
        {{ saveError }}
        <AppButton
          v-if="saveConflict"
          variant="quiet"
          size="sm"
          :label="t('content.editor.reload_file')"
          data-testid="content-reload"
          @click="reload"
        />
      </AppBanner>
      <CodeEditor
        v-model="draft"
        class="content-panel__editor-control dp-panel-scroll"
        bare
        :filename="editor.data.value.filename"
        :language-hint="editor.data.value.language_hint"
        :validation="editor.data.value.validation"
        :readonly="!writable"
        data-testid="content-editor"
      />
    </div>
  </div>
</template>

<style scoped>
.content-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
}
.content-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
}
.content-panel__actions {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
}
.content-panel__kind,
.content-panel__dirty {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
}
.content-panel__editor {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  padding: var(--dp-space-2) 0 0;
}
.content-panel__notice {
  flex: none;
  margin-bottom: var(--dp-space-2);
}
.content-panel__editor-control {
  flex: 1;
  min-height: 0;
}
</style>
