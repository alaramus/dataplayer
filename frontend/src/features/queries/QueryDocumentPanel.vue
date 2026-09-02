<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, toRef, useTemplateRef, watch } from "vue"

import type { ExplainResult, PreparedScript, StatementPublic } from "@/client"
import CodeEditor from "@/features/content/CodeEditor.vue"
import {
  useCreateQueryDocument,
  useQueryDocument,
  useSaveQueryDocument,
  useTrashQueryDocument,
} from "@/features/queries/api"
import {
  bindingsOf,
  elapsed,
  parameterForm,
  ready,
  targetFor,
  toRemember,
  wholeDocument,
} from "@/features/queries/console"
import type { ParameterEntry, RunTarget } from "@/features/queries/console"
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
import ExplainView from "@/features/queries/ExplainView.vue"
import ParameterForm from "@/features/queries/ParameterForm.vue"
import TransactionBar from "@/features/queries/TransactionBar.vue"
import WriteMode from "@/features/queries/WriteMode.vue"
import RunOutcome from "@/features/queries/RunOutcome.vue"
import {
  marks,
  metadataStatus,
  relationsInUse,
  schemasInUse,
  suggestions,
} from "@/features/queries/intelligence"
import {
  useCancelRun,
  useCloseWrites,
  useEndTransaction,
  useExplainQuery,
  useFormatQuery,
  useOpenTransaction,
  useOpenWrites,
  useRehearseChange,
  useSchemaInvalidation,
  useTransaction,
  useUnlockState,
  usePrepareQuery,
  useQueryMetadata,
  useQueryProfile,
  useRun,
  useStartRun,
} from "@/features/queries/runs"
import {
  blockedReason,
  needsRehearsal,
  rehearsalReport,
} from "@/features/queries/structure"
import { useClosable } from "@/features/workspace/closable"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf, statusOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppIconButton,
  AppInput,
  AppSpinner,
  useConfirm,
  useToast,
} from "@/shared/ui"

/**
 * One console: a document above, what it produced below (D65).
 *
 * Run follows the convention without importing an IDE shell. Ctrl+Enter runs
 * the selection or the statement under the caret and never falls back to the
 * whole document; Ctrl+Shift+Enter is the deliberately different command that
 * runs all of it. Where the statements are is the source's answer rather than
 * this screen's — the browser does not split SQL (D62).
 */

const props = defineProps<{ panelId: string; documentId: string }>()

const workspace = useWorkspaceActions()
const toast = useToast()
const confirm = useConfirm()
const document = useQueryDocument(toRef(props, "documentId"))
const save = useSaveQueryDocument()
const create = useCreateQueryDocument()
const trash = useTrashQueryDocument()
const prepare = usePrepareQuery()
const startRun = useStartRun()
const cancelRun = useCancelRun()
const formatting = useFormatQuery()
const explaining = useExplainQuery()
const openWrites = useOpenWrites()
const closeWrites = useCloseWrites()
const openTransaction = useOpenTransaction()
const endTransaction = useEndTransaction()
const rehearse = useRehearseChange()
const forgetStale = useSchemaInvalidation()

/** How long typing has to stop before a save is worth spending a revision on. */
const AUTOSAVE_PAUSE = 800
/** And before asking the source where the statements are. */
const PREPARE_PAUSE = 400
/** Below this the two halves would be two unusable slivers (D65). */
const NARROW = 640

const draft = ref<DraftState>({ body: "", title: null, wrap: false, split: 0.6 })
const state = ref<SaveState>("saved")
const shadowOffer = ref<{ body: string; title: string | null } | null>(null)
const failure = ref("")
const selection = ref({ from: 0, to: 0 })
const script = ref<PreparedScript | null>(null)
const parameters = ref<ParameterEntry[]>([])
const runId = ref<string | null>(null)
const keptRunId = ref<string | null>(null)
const pinned = ref(false)
const startedAt = ref(0)
const now = ref(0)
const plan = ref<ExplainResult | null>(null)
/**
 * What this console may do, chosen every time it is opened.
 *
 * Never restored from anywhere: a document opens read-only, and leaving that
 * is a movement somebody makes deliberately in front of this screen (D66).
 */
const mode = ref<"read" | "auto_commit" | "manual">("read")
const transactionId = ref<string | null>(null)
const narrow = ref(false)
const showing = ref<"editor" | "results">("editor")
const frame = useTemplateRef<HTMLElement>("frame")

let pending: ReturnType<typeof setTimeout> | null = null
let preparing: ReturnType<typeof setTimeout> | null = null
// The text the statements below were found in. Run compares against it rather
// than trusting whatever the last debounced answer happened to be: pressing
// Run a moment after typing must not run yesterday's parse.
let preparedFor: string | null = null
let ticking: ReturnType<typeof setInterval> | null = null
let observer: ResizeObserver | null = null
let loadedId = ""

const server = computed(() => document.data.value)
const connectorId = computed(() => server.value?.connector_id ?? null)
const profile = useQueryProfile(connectorId)
const unlockState = useUnlockState(connectorId)
const transaction = useTransaction(transactionId)
/**
 * What this connection holds, asked for progressively (D65).
 *
 * The schemas of the context first; the columns of a relation once the text
 * names one. Nothing here reads a database to fill a dropdown.
 */
const metadata = useQueryMetadata(connectorId, () => ({
  search_path: [
    ...(server.value?.search_path ?? []),
    ...schemasInUse(script.value),
  ].slice(0, 32),
  relations: relationsInUse(script.value).slice(0, 50),
}))
const offered = computed(() => suggestions(metadata.data.value, script.value))
const editorMarks = computed(() => marks(script.value, metadata.data.value))
const knowledge = computed(() =>
  connectorId.value === null ? "" : metadataStatus(metadata.data.value)
)
const run = useRun(runId)
const kept = useRun(keptRunId)
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

const runnable = computed(
  () => connectorId.value !== null && profile.data.value !== undefined
)
const going = computed(() =>
  ["accepted", "running", "cancelling"].includes(run.data.value?.status ?? "")
)
const canRun = computed(
  () =>
    runnable.value &&
    !going.value &&
    ready(parameters.value) &&
    (mode.value === "read" || unlockState.data.value?.unlocked === true)
)
/** What the statements about to run would do that cannot be undone (D66). */
const risky = computed(() => {
  const statements = script.value?.statements ?? []
  const mutating = statements.filter(
    (statement) => statement.kind === "dml" || statement.kind === "ddl"
  )
  if (mutating.length === 0) return false
  return mutating.some((statement) => statement.risk === "high") || statements.length > 1
})
/**
 * What the result area shows.
 *
 * While a run is going the one before it stays readable and says it is the
 * previous one; a pinned result stays whatever happens next (D65).
 */
const shown = computed(() => {
  if (pinned.value && kept.data.value !== undefined) return kept.data.value
  if (going.value && kept.data.value !== undefined) return kept.data.value
  return run.data.value
})
const showingPrevious = computed(
  () => shown.value !== undefined && shown.value.id !== run.data.value?.id
)
const running = computed(() =>
  going.value ? elapsed(Math.max(0, now.value - startedAt.value)) : ""
)

/**
 * The bar answers as soon as a run does, not at the next poll.
 *
 * The transaction is asked every five seconds because it also expires without
 * anybody touching it. But a run that has just finished is a change this
 * screen already knows about, and a commit preview still saying "0 changing
 * statements" under a statement that has visibly succeeded is the one moment
 * it must not be behind (D66).
 */
watch(going, async (now, before) => {
  if (before && !now && transactionId.value !== null) await transaction.refetch()
})

/**
 * What a finished run changed about the source stops being cached (D66).
 *
 * Only what the source itself issued, and only once: an auto-commit run's
 * effect arrives with the run because it committed with it, while a manual
 * run has nothing to issue until somebody commits the transaction.
 */
watch(
  () => run.data.value?.effect,
  async (effect) => {
    const connector = connectorId.value
    if (effect === null || effect === undefined || connector === null) return
    await forgetStale(connector, effect)
  }
)

useReloadable(props.panelId, async () => {
  await document.refetch()
})

/**
 * An open transaction is not left behind by closing the tab (D66).
 *
 * Two ways out rather than three: keeping it open, or rolling it back and
 * going. Committing is deliberately not offered here — a commit is a decision
 * made while looking at what it would commit, which is the bar above the
 * editor, and the tab closing is not where somebody decides that.
 */
useClosable(props.panelId, async () => {
  if (transactionId.value === null) return true
  const leaving = await confirm({
    title: "Roll back the open transaction?",
    message:
      "This console is holding a transaction open. Closing it rolls back " +
      "everything it has done. Commit it first if you want to keep it.",
    confirmLabel: "Roll back and close",
    cancelLabel: "Keep it open",
    danger: true,
  })
  if (!leaving) return false
  await endTheTransaction(false)
  return true
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
    schedulePrepare()
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

watch(
  () => draft.value.body,
  () => schedulePrepare()
)

// The form follows what the source found, keeping whatever is already filled
// in and whatever the document remembers.
watch([script, server] as const, ([found, loaded]) => {
  parameters.value = parameterForm(
    found?.parameters ?? [],
    loaded?.parameters ?? {},
    parameters.value
  )
})

function schedule() {
  if (pending !== null) clearTimeout(pending)
  pending = setTimeout(() => {
    pending = null
    void autosave()
  }, AUTOSAVE_PAUSE)
}

function schedulePrepare() {
  if (preparing !== null) clearTimeout(preparing)
  preparing = setTimeout(() => {
    preparing = null
    void askWhereStatementsAre()
  }, PREPARE_PAUSE)
}

async function askWhereStatementsAre() {
  const connector = connectorId.value
  const text = draft.value.body
  if (connector === null || text.trim() === "") {
    script.value = null
    preparedFor = null
    return
  }
  try {
    script.value = await prepare.mutateAsync({ connector_id: connector, text })
    preparedFor = text
  } catch {
    // Nothing is said: a source that cannot be asked right now is a Run that
    // will say so when it is pressed, not a red mark while somebody types.
    script.value = null
    preparedFor = null
  }
}

/** The statements in what is on screen now, asking again if that has moved. */
async function currentScript(): Promise<PreparedScript | null> {
  if (script.value === null || preparedFor !== draft.value.body) {
    await askWhereStatementsAre()
  }
  return script.value
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

/** Run what Ctrl+Enter means: the selection, or the statement under the caret. */
async function runHere() {
  const current = await currentScript()
  if (current === null) return
  await go(targetFor(current, draft.value.body, selection.value))
}

/** Run the document, said explicitly. */
async function runEverything() {
  const current = await currentScript()
  if (current === null) return
  await go(wholeDocument(current, draft.value.body))
}

async function go(target: RunTarget | null) {
  const loaded = server.value
  const connector = connectorId.value
  if (target === null || loaded === undefined || connector === null) return
  if (!ready(parameters.value)) {
    toast.info("Fill in the parameters this query asks for")
    return
  }
  // Asked every time, with what it would do in front of the person (D66).
  if (risky.value) {
    const rehearsed = needsRehearsal(script.value) ? await tryItOut(target) : null
    if (rehearsed === "blocked") return
    const tried =
      rehearsed === null || rehearsed === ""
        ? ""
        : "\n\nTried out on the source, then undone:\n" + rehearsed
    const accepted = await confirm({
      title: "Run something that cannot be undone?",
      message:
        `This changes ${loaded.connector_label ?? "the source"} and there is no ` +
        "undo. In a transaction you can still roll it back; with auto-commit " +
        "you cannot." +
        tried,
      confirmLabel: "Run it",
      danger: true,
    })
    if (!accepted) return
  }
  // A transaction is opened when the first statement needs one, not when the
  // mode is chosen: an empty transaction would hold a connection for nothing.
  if (mode.value === "manual" && transactionId.value === null) {
    try {
      const opened = await openTransaction.mutateAsync({
        connector_id: connector,
        document_id: loaded.id,
      })
      transactionId.value = opened.id
    } catch (cause) {
      toast.error(messageOf(cause, "Could not open a transaction"))
      return
    }
  }
  // What is on screen now becomes what stays on screen while the next runs.
  if (run.data.value !== undefined && !pinned.value) keptRunId.value = run.data.value.id
  try {
    const started = await startRun.mutateAsync({
      run_id: crypto.randomUUID(),
      connector_id: connector,
      document_id: loaded.id,
      document_revision: loaded.revision,
      text: target.text,
      range_start: target.start,
      range_end: target.end,
      scope: target.scope,
      mode: mode.value,
      transaction_id: mode.value === "manual" ? transactionId.value : null,
      confirm_high_risk: risky.value,
      parameters: bindingsOf(parameters.value),
    })
    plan.value = null
    runId.value = started.id
    startedAt.value = Date.now()
    now.value = Date.now()
    await rememberValues()
  } catch (cause) {
    toast.error(messageOf(cause, "This query was not run"))
  }
}

/** Keep the values whose row says to keep them, and never a secret one. */
async function rememberValues() {
  const loaded = server.value
  if (loaded === undefined) return
  const wanted = toRemember(parameters.value)
  if (JSON.stringify(wanted) === JSON.stringify(loaded.parameters ?? {})) return
  try {
    await save.mutateAsync({
      documentId: loaded.id,
      body: { revision: loaded.revision, parameters: wanted },
    })
  } catch {
    // Remembering is a convenience; failing at it is not worth interrupting a
    // run that has already started.
  }
}

/**
 * Plan what would be run, without running it.
 *
 * The same statement Run would take — the selection, or the one under the
 * caret — because a plan of something else would answer a question nobody
 * asked (D65).
 */
async function explain() {
  const current = await currentScript()
  const loaded = server.value
  const connector = connectorId.value
  if (current === null || loaded === undefined || connector === null) return
  const target = targetFor(current, draft.value.body, selection.value)
  if (target === null) return
  try {
    plan.value = await explaining.mutateAsync({
      connectorId: connector,
      body: {
        text: target.text,
        document_id: loaded.id,
        parameters: bindingsOf(parameters.value),
      },
    })
    if (narrow.value) showing.value = "results"
  } catch (cause) {
    toast.error(messageOf(cause, "This statement could not be planned"))
  }
}

/**
 * Lay the document, or just what is selected, out again.
 *
 * The source formats it, because how a dialect looks is the dialect's. One
 * replacement, so one undo takes it back, and autosave never does this on
 * anybody's behalf (D65).
 */
async function format(scope: "document" | "selection") {
  const connector = connectorId.value
  if (connector === null) return
  const selected =
    scope === "selection" && selection.value.to > selection.value.from
      ? { from: selection.value.from, to: selection.value.to }
      : null
  const text =
    selected === null
      ? draft.value.body
      : draft.value.body.slice(selected.from, selected.to)
  if (text.trim() === "") return
  try {
    const laid = await formatting.mutateAsync({ connectorId: connector, text })
    draft.value = {
      ...draft.value,
      body:
        selected === null
          ? laid.text
          : draft.value.body.slice(0, selected.from) +
            laid.text +
            draft.value.body.slice(selected.to),
    }
  } catch (cause) {
    toast.error(messageOf(cause, "Could not format this query"))
  }
}

async function unlockWrites(typedName: string) {
  const connector = connectorId.value
  if (connector === null) return
  try {
    await openWrites.mutateAsync({ connectorId: connector, connectorName: typedName })
  } catch (cause) {
    toast.error(messageOf(cause, "Writing was not unlocked"))
  }
}

async function lockWrites() {
  const connector = connectorId.value
  if (connector === null) return
  await closeWrites.mutateAsync(connector)
  mode.value = "read"
}

/** End the transaction, and say what became of what it did. */
async function endTheTransaction(commit: boolean) {
  const id = transactionId.value
  const connector = connectorId.value
  if (id === null) return
  try {
    const answer = await endTransaction.mutateAsync({ transactionId: id, commit })
    transactionId.value = null
    toast.success(answer.message)
    // A commit is when what its statements changed became true, so it is when
    // what was read before them stops being an answer (D66).
    if (connector !== null) await forgetStale(connector, answer.effect)
    if (run.data.value !== undefined) await run.refetch()
  } catch (cause) {
    toast.error(messageOf(cause, "Could not end this transaction"))
  }
}

/**
 * Carry the change out on the source and undo it, before asking (D66).
 *
 * The answer is the source's own — which dependants a cascade would take,
 * whether the drop would be refused at all — rather than a sentence this
 * screen composed about SQL it read. A rehearsal that could not take its
 * locks stops the run: nothing was learnt, so there is nothing to agree to.
 */
async function tryItOut(target: RunTarget): Promise<string | "blocked" | null> {
  const connector = connectorId.value
  const loaded = server.value
  if (connector === null || loaded === undefined) return null
  try {
    const rehearsal = await rehearse.mutateAsync({
      connector_id: connector,
      text: target.text,
      document_id: loaded.id,
      transaction_id: mode.value === "manual" ? transactionId.value : null,
      parameters: bindingsOf(parameters.value),
    })
    const blocked = blockedReason(rehearsal)
    if (blocked !== null) {
      toast.error(blocked)
      return "blocked"
    }
    return rehearsalReport(rehearsal)
  } catch (cause) {
    // The rehearsal is what the person reads before answering, not a gate:
    // the checks that decide whether this may run are the server's, and they
    // are about to be made again by the run itself.
    toast.info(messageOf(cause, "This change could not be tried out first"))
    return null
  }
}

async function stop() {
  const active = run.data.value
  if (active === undefined) return
  try {
    await cancelRun.mutateAsync(active.id)
  } catch (cause) {
    toast.error(messageOf(cause, "Could not stop this query"))
  }
}

function promote(statement: StatementPublic) {
  if (statement.result_id === null || statement.result_id === undefined) return
  workspace.openQueryResult({
    resultId: statement.result_id,
    title: draft.value.title ?? "Query result",
  })
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

/** Drag the line between the two halves; where it ends up is remembered. */
function startResize(event: PointerEvent) {
  const host = frame.value
  if (host === null) return
  const box = host.getBoundingClientRect()
  const move = (moved: PointerEvent) => {
    const ratio = (moved.clientY - box.top) / box.height
    draft.value = { ...draft.value, split: Math.min(0.9, Math.max(0.1, ratio)) }
  }
  const stopResizing = () => {
    window.removeEventListener("pointermove", move)
    window.removeEventListener("pointerup", stopResizing)
  }
  window.addEventListener("pointermove", move)
  window.addEventListener("pointerup", stopResizing)
  event.preventDefault()
}

onMounted(() => {
  ticking = setInterval(() => {
    now.value = Date.now()
  }, 200)
  const host = frame.value
  if (host !== null && typeof ResizeObserver !== "undefined") {
    observer = new ResizeObserver(([entry]) => {
      narrow.value = (entry?.contentRect.width ?? NARROW) < NARROW
    })
    observer.observe(host)
  }
})

onBeforeUnmount(() => {
  if (pending !== null) clearTimeout(pending)
  if (preparing !== null) clearTimeout(preparing)
  if (ticking !== null) clearInterval(ticking)
  observer?.disconnect()
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
        v-if="knowledge"
        class="query-panel__knowledge"
        data-testid="query-knowledge"
      >{{ knowledge }}</span>
      <span
        class="query-panel__state"
        :data-state="state"
        data-testid="query-state"
      >{{ stateLabel }}</span>

      <span
        v-if="going"
        class="query-panel__elapsed"
        data-testid="query-elapsed"
      >{{ running }}</span>
      <AppButton
        v-if="going"
        variant="secondary"
        size="sm"
        label="Cancel"
        data-testid="query-cancel"
        @click="stop"
      />
      <template v-else>
        <AppButton
          variant="primary"
          size="sm"
          label="Run"
          :disable="!canRun"
          data-testid="query-run"
          @click="runHere"
        />
        <AppButton
          v-if="profile.data.value?.supports_explain === true"
          variant="secondary"
          size="sm"
          label="Explain"
          :disable="!canRun || explaining.isPending.value"
          data-testid="query-explain"
          @click="explain"
        />
        <AppButton
          variant="secondary"
          size="sm"
          label="Run script"
          :disable="!canRun"
          data-testid="query-run-script"
          @click="runEverything"
        />
      </template>

      <AppIconButton
        v-if="profile.data.value?.supports_formatting === true"
        icon="format_align_left"
        :tooltip="
          selection.to > selection.from ? 'Format the selection' : 'Format the document'
        "
        :disable="formatting.isPending.value"
        data-testid="query-format"
        @click="format(selection.to > selection.from ? 'selection' : 'document')"
      />
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

    <WriteMode
      v-if="profile.data.value !== undefined"
      :mode="mode"
      :unlock="unlockState.data.value"
      :connector-label="connectorLabel"
      :busy="openWrites.isPending.value"
      class="query-panel__mode"
      @update:mode="mode = $event"
      @unlock="unlockWrites"
      @relock="lockWrites"
    />

    <TransactionBar
      v-if="transaction.data.value !== undefined"
      :transaction="transaction.data.value"
      :busy="endTransaction.isPending.value || going"
      @commit="endTheTransaction(true)"
      @rollback="endTheTransaction(false)"
    />

    <ParameterForm
      v-if="parameters.length > 0"
      :entries="parameters"
      class="query-panel__parameters"
      @update:entries="parameters = $event"
    />

    <div
      v-if="narrow"
      class="query-panel__switch"
      data-testid="query-switch"
    >
      <AppButton
        :variant="showing === 'editor' ? 'primary' : 'quiet'"
        size="sm"
        label="Editor"
        data-testid="query-show-editor"
        @click="showing = 'editor'"
      />
      <AppButton
        :variant="showing === 'results' ? 'primary' : 'quiet'"
        size="sm"
        label="Results"
        data-testid="query-show-results"
        @click="showing = 'results'"
      />
    </div>

    <AppSpinner v-if="document.isPending.value" />
    <div
      v-else-if="server !== undefined"
      ref="frame"
      class="query-panel__frame"
    >
      <div
        v-show="!narrow || showing === 'editor'"
        class="query-panel__editor"
        :style="narrow ? undefined : { flex: `${draft.split} 1 0` }"
      >
        <CodeEditor
          :model-value="draft.body"
          filename="query.sql"
          language-hint="sql"
          :wrap="draft.wrap"
          :suggestions="offered"
          :marks="editorMarks"
          class="query-panel__code"
          @update:model-value="draft.body = $event"
          @update:selection="selection = $event"
          @run="runHere"
          @run-script="runEverything"
        />
      </div>

      <div
        v-if="!narrow"
        class="query-panel__separator"
        data-testid="query-split"
        @pointerdown="startResize"
      />

      <div
        v-show="!narrow || showing === 'results'"
        class="query-panel__results"
        :style="narrow ? undefined : { flex: `${1 - draft.split} 1 0` }"
      >
        <ExplainView
          v-if="plan !== null"
          :plan="plan"
          @close="plan = null"
        />
        <RunOutcome
          v-else-if="shown !== undefined"
          :run="shown"
          :stale="showingPrevious"
          @promote="promote"
          @toggle-pin="pinned = !pinned"
        />
        <div
          v-else
          class="query-panel__nothing"
          data-testid="query-nothing-run"
        >
          Ctrl+Enter runs the statement under the caret.
        </div>
      </div>
    </div>
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
  flex: 0 1 200px;
  min-width: 0;
}
.query-panel__context,
.query-panel__knowledge,
.query-panel__state,
.query-panel__elapsed {
  overflow: hidden;
  color: var(--dp-text-muted);
  font-size: 11px;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.query-panel__context {
  flex: 1;
}
.query-panel__knowledge,
.query-panel__state,
.query-panel__elapsed {
  flex: none;
}
.query-panel__state[data-state="conflict"],
.query-panel__state[data-state="unsynchronised"] {
  color: var(--dp-callout-caution);
}
.query-panel__banner,
.query-panel__parameters,
.query-panel__mode,
.query-panel__switch {
  flex: none;
}
.query-panel__switch {
  display: flex;
  gap: 4px;
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
.query-panel__frame {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.query-panel__editor,
.query-panel__results {
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.query-panel__results {
  overflow: hidden;
}
.query-panel__code {
  flex: 1;
  min-height: 0;
}
/* A wide pointer target around a one-pixel line, as everywhere else. */
.query-panel__separator {
  flex: none;
  height: 7px;
  cursor: row-resize;
  background: linear-gradient(var(--dp-separator), var(--dp-separator)) center / 100% 1px
    no-repeat;
}
.query-panel__separator:hover {
  background: linear-gradient(var(--dp-separator-active), var(--dp-separator-active))
    center / 100% 1px no-repeat;
}
.query-panel__nothing {
  padding: 16px;
  color: var(--dp-text-muted);
  font-size: 12px;
}
</style>
