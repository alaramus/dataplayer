<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from "vue"

import type { ExplainResult, PreparedScript, StatementPublic } from "@/client"
import { connectorNameOf, useConnectors } from "@/features/connectors/api"
import CodeEditor from "@/features/content/CodeEditor.vue"
import {
  useCreateQueryDocument,
  useQueryDocument,
  useSaveQueryDocument,
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
  clearDraft,
  clearShadow,
  copyTitle,
  draftOf,
  emptyDraft,
  keepMine,
  readDraft,
  readShadow,
  recoverable,
  saveFor,
  writeDraft,
  writeShadow,
} from "@/features/queries/draft"
import type { DraftState, SaveState } from "@/features/queries/draft"
import ExplainView from "@/features/queries/ExplainView.vue"
import ParameterForm from "@/features/queries/ParameterForm.vue"
import TransactionBar from "@/features/queries/TransactionBar.vue"
import RunOutcome from "@/features/queries/RunOutcome.vue"
import {
  marks,
  metadataStatus,
  parameterPrefix,
  relationsInUse,
  schemasInUse,
  suggestions,
} from "@/features/queries/intelligence"
import {
  useCancelRun,
  useEndTransaction,
  useExplainQuery,
  useFormatQuery,
  useOpenTransaction,
  useRehearseChange,
  useSchemaInvalidation,
  useTransaction,
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
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useClosable } from "@/features/workspace/closable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf, statusOf } from "@/shared/api/errors"
import { useServerLeaveGuard } from "@/shared/servers/leaving"
import {
  AppBanner,
  AppButton,
  AppIconButton,
  AppInput,
  AppSpinner,
  AppTooltip,
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

/**
 * A console is opened outside the library and put into it on request.
 *
 * `documentId` once somebody has pressed Remember, `draftId` until then. The
 * text of an unremembered one lives in this browser tab and nowhere else, so
 * opening a console — from the plus, from a table, from a run in the history —
 * writes nothing anybody has to tidy up afterwards (D65).
 */
const props = defineProps<{
  panelId: string
  documentId?: string
  draftId?: string
  connectorId?: string
  connectorName?: string | null
}>()

const workspace = useWorkspaceActions()
const toast = useToast()
const confirm = useConfirm()
const document = useQueryDocument(computed(() => props.documentId ?? null))
const save = useSaveQueryDocument()
const create = useCreateQueryDocument()
const prepare = usePrepareQuery()
const startRun = useStartRun()
const cancelRun = useCancelRun()
const formatting = useFormatQuery()
const explaining = useExplainQuery()
const openTransaction = useOpenTransaction()
const endTransaction = useEndTransaction()
const rehearse = useRehearseChange()
const forgetStale = useSchemaInvalidation()

/** How long typing has to stop before a save is worth spending a revision on. */
const AUTOSAVE_PAUSE = 800
/** And before asking the source where the statements are. */
const PREPARE_PAUSE = 400

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
 * Whether statements run in a manually held transaction. Permissions are
 * resolved from the connection on every request, not chosen by this editor.
 */
const manualTransaction = ref(false)
const transactionId = ref<string | null>(null)
const frame = useTemplateRef<HTMLElement>("frame")

let pending: ReturnType<typeof setTimeout> | null = null
let preparing: ReturnType<typeof setTimeout> | null = null
// The text the statements below were found in. Run compares against it rather
// than trusting whatever the last debounced answer happened to be: pressing
// Run a moment after typing must not run yesterday's parse.
let preparedFor: string | null = null
let ticking: ReturnType<typeof setInterval> | null = null
let loadedId = ""

const server = computed(() => document.data.value)
/** Whether this console is in the library at all. */
const remembered = computed(() => props.documentId !== undefined)
useServerLeaveGuard(async () => {
  if (save.isPending.value || create.isPending.value) {
    toast.info("Wait for the query to finish saving before switching servers")
    return false
  }
  if (!remembered.value && props.draftId !== undefined) {
    writeDraft(props.draftId, draft.value)
    const stored = readDraft(props.draftId)
    if (stored?.body === draft.value.body && stored.title === draft.value.title) return true
    return await confirm({
      title: "Leave this query behind?",
      message: "Browser storage could not keep this draft. Copy its text before switching if you want to keep it.",
      confirmLabel: "Discard draft",
      danger: true,
    })
  }
  if (["saved", "unremembered"].includes(state.value)) return true
  // A shadow cannot promise recovery after a remote revision changes. Ask
  // explicitly instead of silently treating it as a durable saved document.
  return await confirm({
    title: "Leave unsaved query changes?",
    message: "Save this query or resolve its conflict before switching to keep your changes. Unsaved edits may not be recoverable after switching.",
    confirmLabel: "Switch anyway",
    danger: true,
  })
})
const connectorId = computed(
  () => server.value === undefined ? props.connectorId ?? null : server.value.connector_id
)
const profile = useQueryProfile(connectorId)
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
const offered = computed(() =>
  suggestions(
    metadata.data.value,
    script.value,
    parameterPrefix(profile.data.value?.parameter_syntax)
  )
)
const editorMarks = computed(() => marks(script.value, metadata.data.value))
const knowledge = computed(() =>
  connectorId.value === null ? "" : metadataStatus(metadata.data.value)
)
const run = useRun(runId)
const kept = useRun(keptRunId)
/**
 * What this console's connection is called now, not when it opened. The list
 * is asked first; the label the document carries is the fallback.
 *
 * Under confirmation this is the word a person types back, and the server
 * compares it with the name the connection has now (D66). A document that has
 * arrived answers on its own, null included: null states that the context is
 * gone (D63), and the name the tab opened with must not put a deleted
 * connection back on screen.
 */
const connectors = useConnectors()
const connection = computed(() =>
  connectors.data.value?.data.find((item) => item.id === connectorId.value)
)
const canUseTransaction = computed(() =>
  profile.data.value?.statement_modes.includes("manual") === true &&
  connection.value?.execution_policy !== "read_only" &&
  connection.value?.access !== "read" && connection.value !== undefined
)
const connectorLabel = computed(() => {
  const listed = connectorNameOf(connectors.data.value, connectorId.value)
  if (listed !== null) return listed
  const loaded = server.value
  return loaded === undefined ? props.connectorName ?? null : loaded.connector_label
})
const searchPath = computed(() => server.value?.search_path ?? [])
const error = computed(() =>
  document.isError.value
    ? messageOf(document.error.value, "Could not open this query")
    : ""
)
/** Only states needing attention appear beside the editor commands. */
const STATE_LABELS: Record<SaveState, string> = {
  unremembered: "",
  saved: "",
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
    ready(parameters.value)
)
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
  return transactionId.value === null
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
    workspace.renameQueryDocument(loaded.id, loaded.title, loaded.connector_id)
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

/**
 * A console nobody has kept fills itself from this browser tab.
 *
 * Whatever opened it — the plus, a table, a run in the history — left the text
 * there under this panel's draft id. A reload finds it again; a new browser
 * tab does not, and shows an empty console rather than somebody else's text.
 */
onMounted(() => {
  const draftId = props.draftId
  if (draftId === undefined || remembered.value) return
  draft.value = readDraft(draftId) ?? emptyDraft()
  state.value = "unremembered"
  schedulePrepare()
})

watch(
  draft,
  () => {
    const draftId = props.draftId
    if (!remembered.value) {
      // Nothing is sent anywhere: this one is not in the library, and the tab
      // is the only thing holding it.
      if (draftId !== undefined) writeDraft(draftId, draft.value)
      return
    }
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
  // A run needs a connection and a statement, not a document: what ran is
  // recorded by the run itself, so a console nobody has kept runs and appears
  // in the history exactly like one they have (D63).
  if (target === null || connector === null) return
  if (!ready(parameters.value)) {
    toast.info("Fill in the parameters this query asks for")
    return
  }
  let selectedScript: PreparedScript
  try {
    // The selection can have a different class than another statement in the
    // document. Use the source's answer for exactly the text being run.
    selectedScript = await prepare.mutateAsync({ connector_id: connector, text: target.text })
  } catch (cause) {
    toast.error(messageOf(cause, "This query could not be prepared"))
    return
  }
  const statements = selectedScript.statements
  const mutating = statements.some((one) => one.kind === "dml" || one.kind === "ddl")
  const risky = mutating && (statements.length > 1 || statements.some((one) => one.kind === "ddl" || one.risk === "high"))
  const supportsWrites = profile.data.value?.statement_modes.includes("auto_commit") ?? true
  const policyConfirm = mutating && supportsWrites && (connection.value?.execution_policy ?? "confirm_writes") === "confirm_writes"
  const mode = manualTransaction.value ? "manual" : mutating && supportsWrites ? "auto_commit" : "read"
  // The connection's confirmation policy and dangerous changes ask at Run,
  // not through an independent permission switch in the editor (D160).
  if ((risky && supportsWrites) || policyConfirm) {
    const rehearsed = risky && needsRehearsal(selectedScript) ? await tryItOut(target) : null
    if (rehearsed === "blocked") return
    const tried =
      rehearsed === null || rehearsed === ""
        ? ""
        : "\n\nTried out on the source, then undone:\n" + rehearsed
    const accepted = await confirm({
      title: risky ? "Run something that cannot be undone?" : "Confirm this write?",
      message:
        `This changes ${connectorLabel.value ?? "the source"}. ` +
        (mode === "manual"
          ? "You can roll back the open transaction before committing it."
          : "Auto-commit applies the change when the run succeeds.") +
        tried,
      confirmLabel: "Run it",
      danger: true,
    })
    if (!accepted) return
  }
  // A transaction is opened when the first statement needs one, not when the
  // mode is chosen: an empty transaction would hold a connection for nothing.
  if (mode === "manual" && transactionId.value === null) {
    try {
      const opened = await openTransaction.mutateAsync({
        connector_id: connector,
        document_id: loaded?.id ?? null,
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
      document_id: loaded?.id ?? null,
      document_revision: loaded?.revision ?? null,
      text: target.text,
      range_start: target.start,
      range_end: target.end,
      scope: target.scope,
      mode,
      transaction_id: mode === "manual" ? transactionId.value : null,
      confirm_write: policyConfirm,
      confirm_high_risk: risky,
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
  if (current === null || connector === null) return
  const target = targetFor(current, draft.value.body, selection.value)
  if (target === null) return
  try {
    plan.value = await explaining.mutateAsync({
      connectorId: connector,
      body: {
        text: target.text,
        document_id: loaded?.id ?? null,
        parameters: bindingsOf(parameters.value),
      },
    })
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
  if (connector === null) return null
  try {
    const rehearsal = await rehearse.mutateAsync({
      connector_id: connector,
      text: target.text,
      document_id: loaded?.id ?? null,
      transaction_id: manualTransaction.value ? transactionId.value : null,
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
    connectorId: shown.value?.connector_id ?? undefined,
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

/**
 * Put this console into the library, which is what the library is.
 *
 * Until this is pressed the text is in the tab and nowhere else, so nothing a
 * person opened and closed leaves a row behind. Afterwards it is an ordinary
 * document and saves itself as it is typed, which is what a thing somebody
 * asked to keep should do (D65).
 */
async function remember() {
  const connector = connectorId.value
  const draftId = props.draftId
  if (connector === null || remembered.value) return
  state.value = "saving"
  failure.value = ""
  try {
    const kept = await create.mutateAsync({
      connector_id: connector,
      title: draft.value.title,
      body: draft.value.body,
    })
    if (draftId !== undefined) clearDraft(draftId)
    // The same tab, now about a document: it keeps its place in the strip and
    // its results, and the panel is named by what it now holds.
    workspace.rememberedQuery(props.panelId, {
      documentId: kept.id,
      title: kept.title,
      connectorName: kept.connector_label,
    })
    toast.success("Kept in your queries")
  } catch (cause) {
    state.value = "unremembered"
    failure.value = messageOf(cause, "Could not keep this query")
  }
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
      connectorId: copy.connector_id ?? undefined,
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
  if (props.documentId !== undefined) clearShadow(props.documentId)
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
})

onBeforeUnmount(() => {
  if (pending !== null) clearTimeout(pending)
  if (preparing !== null) clearTimeout(preparing)
  if (ticking !== null) clearInterval(ticking)
})
</script>

<template>
  <div class="query-panel">
    <div
      class="query-panel__bar"
      data-testid="query-bar"
    >
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
        :style="{ visibility: knowledge ? 'visible' : 'hidden' }"
        class="query-panel__knowledge"
        data-testid="query-knowledge"
      >{{ knowledge }}</span>
      <span
        v-if="stateLabel"
        class="query-panel__state"
        :data-state="state"
        data-testid="query-state"
      >{{ stateLabel }}</span>

      <span
        v-if="going"
        class="query-panel__elapsed"
        data-testid="query-elapsed"
      >{{ running }}</span>
      <!-- The commands keep the size they asked for. The status beside them
           is on screen only while the first read of the connection lasts, and
           a row that gave it room out of the buttons wrapped their labels onto
           two lines for as long as it was there. -->
      <div class="query-panel__actions">
        <AppButton
          v-if="canUseTransaction || transactionId !== null"
          :variant="manualTransaction ? 'current' : 'quiet'"
          layout="toolbar"
          size="sm"
          :label="manualTransaction ? 'Manual: On' : 'Manual: Off'"
          :aria-pressed="manualTransaction"
          :disable="transactionId !== null"
          class="query-panel__manual-button"
          data-testid="query-manual-transaction"
          @click="manualTransaction = !manualTransaction"
        >
          <AppTooltip>
            {{ manualTransaction ? "Changes wait for Commit or Roll back" : "Changes commit after each run" }}
          </AppTooltip>
        </AppButton>
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
          :icon="appIcons.formatAlignLeft"
          :tooltip="
            selection.to > selection.from ? 'Format the selection' : 'Format the document'
          "
          :disable="formatting.isPending.value"
          data-testid="query-format"
          @click="format(selection.to > selection.from ? 'selection' : 'document')"
        />
        <AppIconButton
          :icon="appIcons.wrapText"
          tooltip="Wrap long lines"
          :aria-pressed="draft.wrap"
          data-testid="query-wrap"
          @click="draft.wrap = !draft.wrap"
        />
        <!-- The one command that puts this console into the library. Until it
             is pressed the text is in this tab and nowhere else, which is why
             the button says what it does rather than "Save". -->
        <AppButton
          variant="quiet"
          layout="toolbar"
          size="sm"
          :icon="appIcons.bookmarkAdd"
          :label="remembered ? 'Remembered' : 'Remember'"
          :disable="remembered || connectorId === null || create.isPending.value"
          class="query-panel__remember-button"
          data-testid="query-remember"
          @click="remember"
        />
        <PanelCommands :panel-id="panelId" />
      </div>
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

    <!-- A console nobody has kept has no document to wait for: it is the text
         in this tab, and it is ready the moment the tab is. -->
    <AppSpinner v-if="remembered && document.isPending.value" />
    <div
      v-else-if="!remembered || server !== undefined"
      ref="frame"
      class="query-panel__frame"
      data-testid="query-frame"
    >
      <div
        class="query-panel__editor"
        :style="{ flex: `${draft.split} 1 0` }"
        data-testid="query-editor-pane"
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
        class="query-panel__separator"
        data-testid="query-split"
        @pointerdown="startResize"
      />

      <div
        class="query-panel__results"
        :style="{ flex: `${1 - draft.split} 1 0` }"
        data-testid="query-results-pane"
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
  gap: var(--dp-space-1);
  padding: var(--dp-space-1);
}
.query-panel__bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  /* Scrolls sideways rather than folding anything away once even the commands
     no longer fit, as the grid's own row does. */
  overflow-x: auto;
}
.query-panel__actions {
  flex: none;
  display: flex;
  align-items: center;
  /* The same gap the bar sets, so the join is invisible. */
  gap: var(--dp-space-2);
}
.query-panel__manual-button,
.query-panel__remember-button {
  flex: none;
  height: var(--dp-form-control-height);
}
.query-panel__manual-button {
  width: 7.5rem;
}
.query-panel__remember-button {
  width: 8rem;
}
.query-panel__title {
  flex: 0 1 200px;
  min-width: 120px;
}
.query-panel__context,
.query-panel__knowledge,
.query-panel__state,
.query-panel__elapsed {
  overflow: hidden;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
  white-space: nowrap;
  text-overflow: ellipsis;
}
.query-panel__context {
  flex: 1 1 auto;
  min-width: 0;
}
/* The state gives way before the commands do. */
.query-panel__state {
  flex: 0 1 auto;
  min-width: 0;
}
/* Reserve its width after the read finishes so the commands stay in place. */
.query-panel__knowledge {
  flex: 0 0 auto;
  width: 180px;
  min-width: 0;
}
/* Outside the group of commands, and so does not carry them along as the
   count of digits in it changes. */
.query-panel__elapsed {
  flex: none;
}
.query-panel__state[data-state="conflict"],
.query-panel__state[data-state="unsynchronised"] {
  color: var(--dp-tone-warning-text);
}
.query-panel__banner,
.query-panel__parameters {
  flex: none;
}
.query-panel__resolve {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--dp-space-3);
}
.query-panel__choices {
  display: flex;
  gap: var(--dp-space-2);
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
  padding: var(--dp-space-4);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
</style>
