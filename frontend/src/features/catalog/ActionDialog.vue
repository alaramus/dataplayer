<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue"

import type { ActionPreview } from "@/client"
import {
  useDownloadAction,
  usePreviewAction,
  usePreviewActionOnSet,
  useRunAction,
} from "@/features/catalog/api"
import {
  groupingChoices,
  needsClipboard,
  nodeSetOf,
  summarize,
  withGroupingChoices,
} from "@/features/catalog/actions"
import { forgetClipboard, heldFor } from "@/features/catalog/clipboard"
import type {
  ActionCommand,
  ActionFailure,
  ActionOutcome,
  Grouping,
} from "@/features/catalog/actions"
import FileToRelationDialog from "@/features/catalog/FileToRelationDialog.vue"
import ModelCodeDialog from "@/features/catalog/ModelCodeDialog.vue"
import TableDesigner from "@/features/tableDesign/TableDesigner.vue"
import { formatSize } from "@/features/catalog/nodes"
import { fieldErrorsFrom, messageOf, statusOf } from "@/shared/api/errors"
import SchemaFields from "@/shared/SchemaForm/SchemaFields.vue"
import { useSchemaForm } from "@/shared/SchemaForm/useSchemaForm"
import {
  AppBanner,
  AppButton,
  AppFileInput,
  AppIconButton,
  AppSection,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { saveNativeDownload } from "@/shared/download"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  command: ActionCommand | null
  connectorId: string
  /** Everything the filled form is applied to, one node at a time. */
  nodeIds: (string | null)[]
  nodeLabel: string
  targetNode?: { label: string; kind: string } | null
  /**
   * The groupings the level offers, for a field that names one of them. The
   * form is told what the field means by the server and what this connection
   * holds by the level; neither of the two knows both.
   */
  groupings?: Grouping[]
}>()

const emit = defineEmits<{
  "update:command": [value: ActionCommand | null]
  done: [outcome: ActionOutcome]
}>()

const toast = useToast()
const confirm = useConfirm()
const runAction = useRunAction()
const downloadAction = useDownloadAction()
const { values, errors, reset, applyServerErrors } = useSchemaForm()

/**
 * What was chosen and has not been sent yet.
 *
 * Choosing stages files; it starts nothing. A list that is wrong can be
 * corrected before any of it leaves the browser, which is the whole reason
 * the picker no longer submits by itself. One list either way: whether the
 * action takes a set decides what the picker offers, not what is held here.
 */
const files = ref<File[]>([])
const failure = ref("")
const conflict = ref(false)
const visibleFields = computed(
  () => props.command?.fields.filter((field) => field.kind !== "hidden") ?? []
)
/**
 * What the model screen chooses between, read off the schema.
 *
 * A workflow screen knows the action it is for and may name its field, the
 * way the file-to-relation screen names the ones it fills. The values and the
 * words for them are still the source's.
 */
const dialectChoices = computed(() => props.command?.choices.dialect ?? [])

/**
 * Every place of this connection something may be made in.
 *
 * The same list a field naming a grouping is turned into, so a screen that
 * asks where a table goes offers what such a field would.
 */
const destinationChoices = computed(() => groupingChoices(props.groupings ?? []))

/** The visible fields, with a field naming a grouping offering the ones there are. */
const formFields = computed(() =>
  withGroupingChoices(visibleFields.value, destinationChoices.value)
)
const conflictField = computed(() =>
  props.command?.fields.find((field) => field.purpose === "file-conflict") ?? null
)

/**
 * How long the form is left alone before the source is asked again.
 *
 * A preview is about the parameters, so it is re-asked as they change; a
 * ticked box is one request, and a field somebody is typing into is not one
 * per character.
 */
const PREVIEW_DELAY_MS = 250

const previewAction = usePreviewAction()
const previewSet = usePreviewActionOnSet()
const preview = ref<ActionPreview | null>(null)
const reviewMissing = computed(() => props.command?.requiresPlanReview === true && (
  props.nodeIds.length !== 1 || !preview.value?.fingerprint || preview.value.blocked === true
))
const previewFailed = ref("")
/** The number of the last question asked, so a late answer is ignored. */
let asked = 0
let timer: ReturnType<typeof setTimeout> | undefined

/** The whole selection, when every part of it is a named node. */
const nodeSet = computed(() => nodeSetOf(props.nodeIds))

/**
 * Whether there is a preview to show at all.
 *
 * One node is previewed by the action's own answer about it. Several are
 * previewed only when the source takes them in one request: an account of a
 * set is one thing the source can describe, while several answers stitched
 * together here would be a claim this component has no right to make.
 */
const previewable = computed(() => {
  const command = props.command
  if (command === null) return false
  if (props.nodeIds.length === 1) return command.previews
  return command.previewsSet && nodeSet.value !== null
})

async function askPreview() {
  const command = props.command
  const nodeId = props.nodeIds[0]
  if (command === null || !previewable.value || nodeId === undefined) return
  const mine = (asked += 1)
  const together = props.nodeIds.length > 1 ? nodeSet.value : null
  try {
    const answer =
      together === null
        ? await previewAction.mutateAsync({
            connectorId: props.connectorId,
            name: command.name,
            nodeId,
            params: { ...values.value },
          })
        : await previewSet.mutateAsync({
            connectorId: props.connectorId,
            name: command.name,
            nodeIds: together,
            params: { ...values.value },
          })
    if (mine !== asked) return
    preview.value = answer
    previewFailed.value = ""
  } catch (cause) {
    if (mine !== asked) return
    preview.value = null
    // Optional previews remain advisory; reviewed plans require a fresh fingerprint.
    previewFailed.value = messageOf(cause, "Could not read what this would do")
  }
}

function schedulePreview() {
  if (timer !== undefined) clearTimeout(timer)
  asked += 1
  if (props.command?.requiresPlanReview) preview.value = null
  if (!previewable.value) return
  timer = setTimeout(() => void askPreview(), PREVIEW_DELAY_MS)
}

function forgetPreview() {
  if (timer !== undefined) clearTimeout(timer)
  // Nothing that is still in flight may land on the next form.
  asked += 1
  preview.value = null
  previewFailed.value = ""
}

/**
 * Whether this form has anything to ask before it runs.
 *
 * Paste is the case where it has not: every parameter it takes is filled from
 * what the catalog is holding and none of them is drawn, so its window was an
 * empty confirmation of a gesture already made — pick up, then put down. It
 * runs at once instead.
 */
const asksNothing = computed(() => {
  const command = props.command
  return (
    command !== null &&
    !command.destructive &&
    !command.takesFile &&
    command.workflow === undefined &&
    !previewable.value &&
    visibleFields.value.length === 0
  )
})

/**
 * Whether a run that asked nothing came back with something to answer.
 *
 * The window still opens then: a refusal is read here, and the two answers to
 * a name already taken are pressed here.
 */
const answering = ref(false)

const open = computed(
  () => props.command !== null && (!asksNothing.value || answering.value)
)
const destructiveQuestion = computed(
  () =>
    props.command?.question ??
    `Are you sure you want to delete ${props.nodeLabel}?`
)

watch(
  () => props.command,
  (command) => {
    failure.value = ""
    conflict.value = false
    answering.value = false
    files.value = []
    forgetPreview()
    reset(command?.fields ?? [], initialValues(command))
    schedulePreview()
    if (command !== null && asksNothing.value) void submit()
  },
  // Immediately, so the form and its preview do not depend on this component
  // having been mounted before the command arrived.
  { immediate: true }
)

// Whatever a run leaves unanswered brings the window up, however it was
// started. Said once here rather than at each of the ways submit() ends.
watch(failure, (message) => {
  if (message !== "") answering.value = true
})

// The answer is about the parameters, so it is asked again when they change.
// Deeply, because the form holds one object for every field it has.
watch(values, schedulePreview, { deep: true, flush: "sync" })
watch(
  () => [props.connectorId, props.nodeIds],
  () => {
    if (props.command?.requiresPlanReview) schedulePreview()
  },
  { deep: true, flush: "sync" }
)

onBeforeUnmount(forgetPreview)

function close() {
  emit("update:command", null)
}

/**
 * A fresh choice from the picker.
 *
 * It is a new attempt, so whatever the last one was refused for is dropped:
 * a taken name was the answer about the files that were there, and these
 * are asked about first like any others.
 */
function choose(chosen: File[]) {
  files.value = chosen
  conflict.value = false
  failure.value = ""
  const field = conflictField.value
  if (field !== null) values.value = { ...values.value, [field.name]: "refuse" }
}

/** Take one file off the list. Nothing was sent, so nothing is undone. */
function forget(index: number) {
  files.value = files.value.filter((_, at) => at !== index)
}

async function submit() {
  const command = props.command
  if (!command) return
  if (command.takesFile && files.value.length === 0) {
    failure.value = "Choose a file first"
    return
  }

  failure.value = ""
  const params = await normalizedParams()
  if (params === null) return
  if (reviewMissing.value) {
    failure.value = "Review the operation plan before running it"
    return
  }
  if (command.downloads) {
    await download(command, params)
    return
  }
  try {
    const outcome = await runAction.mutateAsync({
      connectorId: props.connectorId,
      name: command.name,
      label: command.label,
      nodeIds: props.nodeIds,
      params,
      files: files.value,
      asSet: command.takesSet,
      ...(command.requiresPlanReview && preview.value?.fingerprint
        ? { reviewedFingerprint: preview.value.fingerprint } : {}),
    })
    // A file that was refused keeps the dialog open, because the answer to
    // it is here: take that file off the list, or say what to do about the
    // name. What did land is reported all the same.
    const unfinished = [...outcome.failures, ...(outcome.skipped ?? [])]
    if (unfinished.length > 0 && command.requiresPlanReview) {
      report(unfinished)
      forgetPreview()
      schedulePreview()
      return
    }
    if (unfinished.length > 0 && command.takesFile) {
      emit("done", outcome)
      report(unfinished)
      return
    }
    // One line whatever the size of the set: what was done, and what was
    // refused by whom. A refusal in the middle does not stop the rest.
    const said = summarize(outcome, command.label)
    if (outcome.failures.length > 0) toast.error(said)
    else if (outcome.skipped?.length) toast.info(said)
    else toast.success(said)
    // What was held has landed. Keeping it would offer to paste a file that
    // has just been moved away from where it was picked up.
    if (needsClipboard(command) && unfinished.length === 0) forgetClipboard()
    emit("done", outcome)
    close()
  } catch (cause) {
    // One request was sent, so its refusal arrives as an exception rather
    // than in the outcome. It says the same thing and is read the same way.
    if (command.requiresPlanReview) {
      forgetPreview()
      schedulePreview()
    }
    const fieldErrors = fieldErrorsFrom(cause)
    if (fieldErrors) {
      applyServerErrors(fieldErrors)
      answering.value = true
      return
    }
    const sent = files.value[0]
    report([
      {
        nodeId: props.nodeIds[0] ?? null,
        message: messageOf(cause, "The action could not be performed"),
        ...(sent === undefined ? {} : { file: sent }),
        conflict: statusOf(cause) === 409,
      },
    ])
  }
}

/**
 * A download that had something to ask, sent once the form is filled.
 *
 * It ends here rather than in an outcome: the answer is bytes the browser
 * fetches for itself, and there is nothing for the catalog to re-read.
 */
async function download(command: ActionCommand, params: Record<string, unknown>) {
  const targets = nodeSet.value
  if (targets === null) {
    failure.value = "Choose what to write out"
    return
  }
  try {
    const ready = await downloadAction.mutateAsync({
      connectorId: props.connectorId,
      name: command.name,
      nodeIds: targets,
      params,
    })
    saveNativeDownload(ready.download_url)
    close()
  } catch (cause) {
    failure.value = messageOf(cause, "The download could not be prepared")
  }
}

/**
 * What is left standing after a run that did not finish.
 *
 * A file that was sent leaves the list and a refused one stays in it, so
 * what is on the screen is always what still has to happen. When every
 * refusal is a name already taken and the action has a question about that,
 * the two answers to it are offered in place of the plain message.
 */
function report(failed: ActionFailure[]) {
  const left = failed.flatMap((one) => (one.file === undefined ? [] : [one.file]))
  if (left.length > 0) files.value = left
  conflict.value =
    conflictField.value !== null &&
    left.length === failed.length &&
    failed.length > 0 &&
    failed.every((one) => one.conflict === true)
  failure.value = conflict.value
    ? takenNames(left)
    : failed.map((one) => one.message).join("; ")
}

/** The conflict, in the words the two buttons under it answer. */
function takenNames(taken: File[]): string {
  const first = taken[0]
  if (taken.length === 1 && first !== undefined) {
    return `${first.name} already exists. Replace it or keep both files.`
  }
  return (
    `${String(taken.length)} of these files already exist. ` +
    "Replace them or keep both copies of each."
  )
}

function initialValues(command: ActionCommand | null): Record<string, unknown> {
  if (command === null) return {}
  return { ...nameValues(command), ...clipboardValues(command) }
}

/**
 * What the catalog is holding, put into the fields that asked for it.
 *
 * By purpose and never by name: the source says a field carries what was
 * copied, and this fills it. Nothing here knows that the action is called
 * paste, or what pasting means (D74).
 */
function clipboardValues(command: ActionCommand): Record<string, unknown> {
  const current = heldFor(props.connectorId)
  if (current === null) return {}
  const filled: Record<string, unknown> = {}
  for (const field of command.fields) {
    if (field.purpose === "clipboard-nodes") filled[field.name] = current.nodeIds
    if (field.purpose === "clipboard-mode") filled[field.name] = current.mode
  }
  return filled
}

function nameValues(command: ActionCommand): Record<string, unknown> {
  const node = props.targetNode
  if (node === null || node === undefined) return {}
  return Object.fromEntries(
    command.fields
      .filter((field) => field.purpose === "node-name")
      .map((field) => [
        field.name,
        node.kind === "file" ? splitExtension(node.label).stem : node.label,
      ])
  )
}

function splitExtension(name: string): { stem: string; extension: string } {
  const at = name.lastIndexOf(".")
  if (at <= 0) return { stem: name, extension: "" }
  return { stem: name.slice(0, at), extension: name.slice(at) }
}

async function normalizedParams(): Promise<Record<string, unknown> | null> {
  const params = { ...values.value }
  if (props.targetNode?.kind !== "file") return params
  const original = splitExtension(props.targetNode.label)
  const field = props.command?.fields.find(
    (candidate) => candidate.purpose === "node-name"
  )
  if (field === undefined || original.extension === "") return params
  const typed = String(params[field.name] ?? "")
  const requested = splitExtension(typed)
  if (requested.extension === "") {
    params[field.name] = `${typed}${original.extension}`
    return params
  }
  if (requested.extension === original.extension) return params
  const accepted = await confirm({
    title: "Change file extension?",
    message:
      `Change ${original.extension} to ${requested.extension}? ` +
      "The file contents will not be converted.",
    confirmLabel: "Change extension",
    danger: true,
  })
  return accepted ? params : null
}

function retryConflict(policy: "replace" | "rename") {
  const field = conflictField.value
  if (field === null) return
  conflict.value = false
  values.value = { ...values.value, [field.name]: policy }
  void submit()
}

async function runWorkflow(value: {
  nodeId: string
  file: File
  params: Record<string, unknown>
}) {
  const command = props.command
  if (command === null) return
  failure.value = ""
  try {
    const outcome = await runAction.mutateAsync({
      connectorId: props.connectorId,
      name: command.name,
      nodeIds: [value.nodeId],
      params: value.params,
      label: command.label,
      files: [value.file],
    })
    toast.success(summarize(outcome, command.label))
    emit("done", outcome)
    close()
  } catch (cause) {
    failure.value = messageOf(cause, "The table could not be created")
  }
}

/**
 * A workflow that carries no file: one filled answer, one node.
 *
 * Beside `runWorkflow` rather than folded into it with an optional file: the
 * two differ in what the request is, and a single function taking a file that
 * is sometimes absent reads as though the difference were incidental.
 */
async function runDesign(value: {
  nodeId: string
  params: Record<string, unknown>
}) {
  const command = props.command
  if (command === null) return
  failure.value = ""
  try {
    const outcome = await runAction.mutateAsync({
      connectorId: props.connectorId,
      name: command.name,
      nodeIds: [value.nodeId],
      params: value.params,
      label: command.label,
    })
    toast.success(summarize(outcome, command.label))
    emit("done", outcome)
    close()
  } catch (cause) {
    failure.value = messageOf(cause, "The table could not be created")
  }
}
</script>

<template>
  <!-- A workflow is a screen of its own: the source said the generic form has
       nowhere to put what this answer is. -->
  <ModelCodeDialog
    v-if="command?.workflow === 'model-as-code'"
    :model-value="open"
    :connector-id="connectorId"
    :node-ids="nodeIds.filter((id): id is string => id !== null)"
    :label="nodeLabel"
    :choices="dialectChoices"
    :chosen="String(command?.defaults.dialect ?? '')"
    @update:model-value="close"
  />
  <TableDesigner
    v-else-if="command?.workflow === 'table-designer'"
    :model-value="open"
    :connector-id="connectorId"
    :node-id="String(nodeIds[0] ?? '')"
    :node-label="nodeLabel"
    :destinations="destinationChoices"
    :running="runAction.isPending.value"
    :error="failure"
    @run="runDesign"
    @update:model-value="close"
  />
  <FileToRelationDialog
    v-else-if="command?.workflow === 'file-to-relation'"
    :model-value="open"
    :connector-id="connectorId"
    :initial-schema="String(nodeIds[0] ?? '')"
    :running="runAction.isPending.value"
    :error="failure"
    @run="runWorkflow"
    @update:model-value="close"
  />
  <WindowDialog
    v-else-if="command"
    :model-value="open"
    size="sm"
    :title="nodeLabel ? `${command.label} — ${nodeLabel}` : command.label"
    data-testid="action-dialog"
    @update:model-value="close"
  >
    <AppSection gutter>
      <!-- The question follows the action's declaration rather than a list of
           destructive action names kept by the client. It stays ordinary text:
           the target name is the useful part of this confirmation. -->
      <p
        v-if="command.destructive"
        data-testid="action-confirmation"
      >
        {{ destructiveQuestion }}
      </p>

      <AppBanner
        v-if="failure"
        tone="error"
        data-testid="action-error"
      >
        {{ failure }}
      </AppBanner>

      <AppFileInput
        v-if="command.takesFile"
        :model-value="files"
        :multiple="command.takesManyFiles"
        :append="command.takesManyFiles"
        :disable="runAction.isPending.value"
        :label="command.takesManyFiles ? 'Files' : 'File'"
        data-testid="action-file"
        @update:model-value="choose"
      />

      <!-- What was chosen, before any of it is sent. Choosing a file only
           puts it here, so a list that is wrong is corrected by taking a
           row out of it: that file never leaves the browser. -->
      <ul
        v-if="command.takesFile && files.length > 0"
        class="action-dialog__files"
        data-testid="action-files"
      >
        <li
          v-for="(chosen, index) in files"
          :key="`${String(index)}:${chosen.name}`"
          class="action-dialog__file"
        >
          <span class="action-dialog__file-name">{{ chosen.name }}</span>
          <span class="action-dialog__file-size">{{ formatSize(chosen.size) }}</span>
          <AppIconButton
            icon="close"
            :tooltip="`Take ${chosen.name} off the list`"
            :disable="runAction.isPending.value"
            :data-testid="`action-file-remove-${String(index)}`"
            @click="forget(index)"
          />
        </li>
      </ul>

      <SchemaFields
        v-if="formFields.length"
        v-model="values"
        :fields="formFields"
        :errors="errors"
      />

      <!-- What the source says this would do. Nothing here knows what is
           being previewed: a summary and a list of lines, in its words. -->
      <AppBanner
        v-if="previewFailed"
        tone="warning"
        data-testid="action-preview-error"
      >
        {{ previewFailed }}
      </AppBanner>
      <AppBanner
        v-else-if="preview"
        :tone="preview.blocked ? 'warning' : 'info'"
        data-testid="action-preview"
      >
        <div>{{ preview.summary }}</div>
        <!-- The list is optional in the answer: a source with nothing to add
             says its sentence and stops there. -->
        <ul
          v-if="preview.items?.length"
          class="action-dialog__consequences"
        >
          <li
            v-for="item in preview.items ?? []"
            :key="item"
          >
            {{ item }}
          </li>
        </ul>
      </AppBanner>
    </AppSection>

    <template #actions>
      <AppButton
        variant="quiet"
        :label="runAction.isPending.value ? 'Hide' : 'Cancel'"
        @click="close"
      />
      <AppButton
        v-if="conflict"
        variant="secondary"
        label="Keep both"
        data-testid="action-keep-both"
        @click="retryConflict('rename')"
      />
      <AppButton
        v-if="conflict"
        variant="danger"
        label="Replace"
        data-testid="action-replace"
        @click="retryConflict('replace')"
      />
      <!-- A preview that says the source would refuse turns the button off:
           the answer to "what would happen" was "nothing, and here is why". -->
      <AppButton
        v-else
        :variant="command.destructive ? 'danger' : 'primary'"
        :label="command.label"
        :loading="runAction.isPending.value || downloadAction.isPending.value"
        :disable="preview?.blocked === true || reviewMissing"
        data-testid="action-submit"
        @click="submit"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.action-dialog__files {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 180px;
  overflow: auto;
}

.action-dialog__file {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}

.action-dialog__file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-dialog__file-size {
  opacity: 0.6;
  white-space: nowrap;
}

.action-dialog__consequences {
  margin: 4px 0 0;
  padding-left: 20px;
  max-height: 180px;
  overflow: auto;
}
</style>
