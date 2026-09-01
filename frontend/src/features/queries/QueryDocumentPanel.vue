<script setup lang="ts">
import { computed, onBeforeUnmount, ref, toRef, watch } from "vue"

import CodeEditor from "@/features/content/CodeEditor.vue"
import {
  useCreateQueryDocument,
  useQueryDocument,
  useSaveQueryDocument,
  useTrashQueryDocument,
} from "@/features/queries/api"
import {
  changed,
  clearShadow,
  copyTitle,
  draftOf,
  keepMine,
  readShadow,
  recoverable,
  saveFor,
  writeShadow,
} from "@/features/queries/draft"
import type { DraftState, SaveState } from "@/features/queries/draft"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf, statusOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppIconButton,
  AppInput,
  AppSpinner,
  useToast,
} from "@/shared/ui"

/**
 * One console (D65).
 *
 * There is no Run here yet: this slice is the document — its text, its name,
 * its context and the rules about saving it. What the editor cannot decide on
 * its own it asks the person: a revision conflict has three answers and no
 * silent fourth (D63).
 */

const props = defineProps<{ panelId: string; documentId: string }>()

const workspace = useWorkspaceActions()
const toast = useToast()
const document = useQueryDocument(toRef(props, "documentId"))
const save = useSaveQueryDocument()
const create = useCreateQueryDocument()
const trash = useTrashQueryDocument()

/** How long typing has to stop before a save is worth spending a revision on. */
const AUTOSAVE_PAUSE = 800

const draft = ref<DraftState>({ body: "", title: null, wrap: false })
const state = ref<SaveState>("saved")
const shadowOffer = ref<{ body: string; title: string | null } | null>(null)
const failure = ref("")
let pending: ReturnType<typeof setTimeout> | null = null
let loadedId = ""

const server = computed(() => document.data.value)
const connectorLabel = computed(() => server.value?.connector_label ?? null)
const searchPath = computed(() => server.value?.search_path ?? [])
const error = computed(() =>
  document.isError.value
    ? messageOf(document.error.value, "Could not open this query")
    : ""
)
/** One word for each state, and no state without one. */
const STATE_LABELS: Record<SaveState, string> = {
  saved: "Saved",
  dirty: "Unsaved changes",
  saving: "Saving…",
  conflict: "Changed elsewhere",
  unsynchronised: "Not synchronised",
}
const stateLabel = computed(() => STATE_LABELS[state.value])

useReloadable(props.panelId, async () => {
  await document.refetch()
})

/**
 * Fill the editor from the server, once per document.
 *
 * Once, and not on every answer: this panel is the writer of its own
 * document, so a later answer — including the one its own save produced — must
 * not replace text somebody is in the middle of typing.
 */
watch(
  server,
  (loaded) => {
    if (loaded === undefined || loaded.id === loadedId) return
    loadedId = loaded.id
    draft.value = draftOf(loaded)
    state.value = "saved"
    const shadow = readShadow(loaded.id)
    shadowOffer.value = recoverable(shadow, loaded)
      ? { body: shadow?.body ?? "", title: shadow?.title ?? null }
      : null
    if (shadow !== null && shadowOffer.value === null) clearShadow(loaded.id)
  },
  { immediate: true }
)

watch(
  draft,
  () => {
    const loaded = server.value
    if (loaded === undefined || state.value === "conflict") return
    if (!changed(loaded, draft.value)) {
      if (state.value === "dirty") state.value = "saved"
      return
    }
    state.value = "dirty"
    schedule()
  },
  { deep: true }
)

function schedule() {
  if (pending !== null) clearTimeout(pending)
  pending = setTimeout(() => {
    pending = null
    void autosave()
  }, AUTOSAVE_PAUSE)
}

async function autosave() {
  const loaded = server.value
  if (loaded === undefined) return
  const update = saveFor(loaded, draft.value)
  if (update === null) return
  state.value = "saving"
  failure.value = ""
  try {
    const saved = await save.mutateAsync({ documentId: loaded.id, body: update })
    clearShadow(saved.id)
    // Somebody may have typed while the request was in flight; the state says
    // what is true now rather than what was true when it was sent.
    state.value = changed(saved, draft.value) ? "dirty" : "saved"
    if (state.value === "dirty") schedule()
    if (saved.title !== loaded.title) {
      workspace.renameQueryDocument(saved.id, saved.title)
    }
  } catch (cause) {
    if (statusOf(cause) === 409) {
      state.value = "conflict"
      await document.refetch()
      return
    }
    // The server could not be reached. The text stays on screen, is marked as
    // unsynchronised and is kept in this tab so a reload does not lose it.
    state.value = "unsynchronised"
    failure.value = messageOf(cause, "Could not save this query")
    writeShadow({
      documentId: loaded.id,
      revision: loaded.revision,
      body: draft.value.body,
      title: draft.value.title,
    })
  }
}

async function resolveKeepMine() {
  const remote = server.value
  if (remote === undefined) return
  state.value = "saving"
  try {
    const saved = await save.mutateAsync({
      documentId: remote.id,
      body: keepMine(remote, draft.value),
    })
    clearShadow(saved.id)
    state.value = "saved"
    workspace.renameQueryDocument(saved.id, saved.title)
  } catch (cause) {
    state.value = "conflict"
    failure.value = messageOf(cause, "Could not save this query")
  }
}

function resolveUseRemote() {
  const remote = server.value
  if (remote === undefined) return
  draft.value = draftOf(remote)
  clearShadow(remote.id)
  state.value = "saved"
  failure.value = ""
}

async function resolveSaveACopy() {
  const remote = server.value
  if (remote === undefined || remote.connector_id === null) return
  try {
    const copy = await create.mutateAsync({
      connector_id: remote.connector_id,
      title: copyTitle(draft.value.title),
      body: draft.value.body,
      search_path: remote.search_path,
    })
    clearShadow(remote.id)
    resolveUseRemote()
    workspace.openQueryDocument({
      documentId: copy.id,
      title: copy.title,
      connectorName: copy.connector_label,
    })
    toast.success("Your text was kept as a copy")
  } catch (cause) {
    toast.error(messageOf(cause, "Could not keep your text as a copy"))
  }
}

function takeShadow() {
  const offer = shadowOffer.value
  if (offer === null) return
  draft.value = { ...draft.value, body: offer.body, title: offer.title }
  shadowOffer.value = null
}

function dropShadow() {
  shadowOffer.value = null
  clearShadow(props.documentId)
}

async function moveToTrash() {
  try {
    await trash.mutateAsync(props.documentId)
    clearShadow(props.documentId)
    workspace.closeQueryDocument(props.documentId)
    toast.success("Moved to Trash")
  } catch (cause) {
    toast.error(messageOf(cause, "Could not delete this query"))
  }
}

onBeforeUnmount(() => {
  if (pending !== null) clearTimeout(pending)
})
</script>

<template>
  <div class="query-panel">
    <div class="query-panel__bar">
      <AppInput
        :model-value="draft.title ?? ''"
        placeholder="Untitled query"
        compact
        class="query-panel__title"
        data-testid="query-title"
        @update:model-value="draft.title = $event.trim() === '' ? null : $event"
      />
      <span
        class="query-panel__context"
        data-testid="query-context"
      >
        {{ connectorLabel ?? "Connection unavailable" }}
        <template v-if="searchPath.length > 0"> · {{ searchPath.join(", ") }}</template>
      </span>
      <span
        class="query-panel__state"
        :data-state="state"
        data-testid="query-state"
      >{{ stateLabel }}</span>
      <AppIconButton
        icon="wrap_text"
        tooltip="Wrap long lines"
        :aria-pressed="draft.wrap"
        data-testid="query-wrap"
        @click="draft.wrap = !draft.wrap"
      />
      <AppIconButton
        icon="delete"
        tooltip="Move to Trash"
        data-testid="query-trash"
        @click="moveToTrash"
      />
    </div>

    <AppBanner
      v-if="error"
      tone="error"
      class="query-panel__banner"
      data-testid="query-error"
    >
      {{ error }}
    </AppBanner>

    <AppBanner
      v-else-if="state === 'conflict'"
      tone="warning"
      class="query-panel__banner"
      data-testid="query-conflict"
    >
      <div class="query-panel__resolve">
        <span>This query changed elsewhere. Which text should stay?</span>
        <div class="query-panel__choices">
          <AppButton
            variant="secondary"
            size="sm"
            label="Keep mine"
            data-testid="conflict-keep-mine"
            @click="resolveKeepMine"
          />
          <AppButton
            variant="secondary"
            size="sm"
            label="Use theirs"
            data-testid="conflict-use-remote"
            @click="resolveUseRemote"
          />
          <AppButton
            variant="secondary"
            size="sm"
            label="Save mine as a copy"
            data-testid="conflict-save-a-copy"
            @click="resolveSaveACopy"
          />
        </div>
      </div>
    </AppBanner>

    <AppBanner
      v-else-if="state === 'unsynchronised'"
      tone="warning"
      class="query-panel__banner"
      data-testid="query-unsynchronised"
    >
      {{ failure }} Your text is kept in this browser tab until it saves.
    </AppBanner>

    <AppBanner
      v-if="shadowOffer !== null"
      tone="info"
      class="query-panel__banner"
      data-testid="query-shadow"
    >
      <div class="query-panel__resolve">
        <span>This tab holds text that was never saved.</span>
        <div class="query-panel__choices">
          <AppButton
            variant="secondary"
            size="sm"
            label="Put it back"
            data-testid="shadow-restore"
            @click="takeShadow"
          />
          <AppButton
            variant="quiet"
            size="sm"
            label="Discard"
            data-testid="shadow-discard"
            @click="dropShadow"
          />
        </div>
      </div>
    </AppBanner>

    <AppSpinner v-if="document.isPending.value" />
    <CodeEditor
      v-else-if="server !== undefined"
      :model-value="draft.body"
      filename="query.sql"
      language-hint="sql"
      :wrap="draft.wrap"
      class="query-panel__editor"
      @update:model-value="draft.body = $event"
    />
  </div>
</template>

<style scoped>
.query-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 4px;
  padding: 4px;
}
.query-panel__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
}
.query-panel__title {
  flex: 0 1 240px;
  min-width: 0;
}
.query-panel__context,
.query-panel__state {
  overflow: hidden;
  color: var(--dp-text-muted);
  font-size: 11px;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.query-panel__context {
  flex: 1;
}
.query-panel__state {
  flex: none;
}
.query-panel__state[data-state="conflict"],
.query-panel__state[data-state="unsynchronised"] {
  color: var(--dp-callout-caution);
}
.query-panel__banner {
  flex: none;
}
.query-panel__resolve {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.query-panel__choices {
  display: flex;
  gap: 8px;
}
.query-panel__editor {
  flex: 1;
  min-height: 0;
}
</style>
