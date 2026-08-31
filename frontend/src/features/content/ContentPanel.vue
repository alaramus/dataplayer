<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { EditorContent, EditorContentRequest } from "@/client"
import CodeEditor from "@/features/content/CodeEditor.vue"
import { useEditorContent, useUpdateContent } from "@/features/content/api"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf, statusOf } from "@/shared/api/errors"
import { AppBanner, AppButton, AppSpinner, useToast } from "@/shared/ui"

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
const updateContent = useUpdateContent(connectorId)
const workspace = useWorkspaceActions()
const toast = useToast()

const draft = ref("")
const baseline = ref("")
const loadedVersion = ref<string | null>(null)
const saveError = ref("")
const saveConflict = ref(false)

const dirty = computed(() => draft.value !== baseline.value)
const writable = computed(() => editor.data.value?.writable === true)
const canSave = computed(() => writable.value && loadedVersion.value !== null && dirty.value)
const error = computed(() =>
  editor.isError.value ? messageOf(editor.error.value, "Could not open this file") : ""
)
const kindLabel = computed(() =>
  props.representation === "jsonl" ? "JSON lines" : props.representation.toUpperCase()
)

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
useReloadable(props.panelId, async () => {
  if (dirty.value) {
    toast.info("This file has unsaved changes; save or undo them before reloading")
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
    toast.success(`${props.title} saved`)
  } catch (cause) {
    saveError.value = messageOf(cause, "Could not save this file")
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
        <span
          v-if="dirty"
          class="content-panel__dirty"
          data-testid="content-dirty"
        >
          Unsaved changes
        </span>
        <AppButton
          v-if="writable"
          variant="primary"
          size="sm"
          icon="save"
          label="Save"
          :loading="updateContent.isPending.value"
          :disable="!canSave"
          data-testid="content-save"
          @click="save"
        />
        <AppButton
          v-if="tableTitle"
          variant="quiet"
          size="sm"
          icon="grid_on"
          :label="tableTitle"
          data-testid="content-view-table"
          @click="showTable"
        />
      </div>
    </div>

    <AppBanner
      v-if="error"
      tone="error"
      data-testid="content-error"
    >
      {{ error }}
    </AppBanner>

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
          label="Reload file"
          data-testid="content-reload"
          @click="reload"
        />
      </AppBanner>
      <CodeEditor
        v-model="draft"
        class="content-panel__editor-control"
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
  padding: 4px;
}
.content-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 8px;
  border-bottom: 1px solid var(--dp-border-faint);
}
.content-panel__actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.content-panel__kind,
.content-panel__dirty {
  color: var(--dp-text-muted);
  font-size: 11px;
}
.content-panel__editor {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  padding: 8px;
}
.content-panel__notice {
  flex: none;
  margin-bottom: 8px;
}
.content-panel__editor-control {
  flex: 1;
  min-height: 0;
}
</style>
