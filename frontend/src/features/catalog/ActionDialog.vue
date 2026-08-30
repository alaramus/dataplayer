<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue"

import type { ActionPreview } from "@/client"
import { usePreviewAction, useRunAction } from "@/features/catalog/api"
import { summarize } from "@/features/catalog/actions"
import type { ActionCommand, ActionOutcome } from "@/features/catalog/actions"
import { fieldErrorsFrom, messageOf } from "@/shared/api/errors"
import SchemaFields from "@/shared/SchemaForm/SchemaFields.vue"
import { useSchemaForm } from "@/shared/SchemaForm/useSchemaForm"
import {
  AppBanner,
  AppButton,
  AppFileInput,
  AppSection,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

const props = defineProps<{
  command: ActionCommand | null
  connectorId: string
  /** Everything the filled form is applied to, one node at a time. */
  nodeIds: (string | null)[]
  nodeLabel: string
}>()

const emit = defineEmits<{
  "update:command": [value: ActionCommand | null]
  done: [outcome: ActionOutcome]
}>()

const toast = useToast()
const runAction = useRunAction()
const { values, errors, reset, applyServerErrors } = useSchemaForm()

const file = ref<File | null>(null)
const failure = ref("")

/**
 * How long the form is left alone before the source is asked again.
 *
 * A preview is about the parameters, so it is re-asked as they change; a
 * ticked box is one request, and a field somebody is typing into is not one
 * per character.
 */
const PREVIEW_DELAY_MS = 250

const previewAction = usePreviewAction()
const preview = ref<ActionPreview | null>(null)
const previewFailed = ref("")
/** The number of the last question asked, so a late answer is ignored. */
let asked = 0
let timer: ReturnType<typeof setTimeout> | undefined

/**
 * Whether there is a preview to show at all.
 *
 * One node, because a preview is about one: a form applied to several would
 * come back as several answers, and nothing here knows what to call each of
 * them. No action offered for a set previews today.
 */
const previewable = computed(
  () => props.command?.previews === true && props.nodeIds.length === 1
)

async function askPreview() {
  const command = props.command
  const nodeId = props.nodeIds[0]
  if (command === null || !previewable.value || nodeId === undefined) return
  const mine = (asked += 1)
  try {
    const answer = await previewAction.mutateAsync({
      connectorId: props.connectorId,
      name: command.name,
      nodeId,
      params: { ...values.value },
    })
    if (mine !== asked) return
    preview.value = answer
    previewFailed.value = ""
  } catch (cause) {
    if (mine !== asked) return
    preview.value = null
    // Said rather than swallowed, and it does not stop the action: not knowing
    // what would happen is a reason to be careful, not a refusal.
    previewFailed.value = messageOf(cause, "Could not read what this would do")
  }
}

function schedulePreview() {
  if (timer !== undefined) clearTimeout(timer)
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

const open = computed(() => props.command !== null)

watch(
  () => props.command,
  (command) => {
    failure.value = ""
    file.value = null
    forgetPreview()
    reset(command?.fields ?? [])
    schedulePreview()
  },
  // Immediately, so the form and its preview do not depend on this component
  // having been mounted before the command arrived.
  { immediate: true }
)

// The answer is about the parameters, so it is asked again when they change.
// Deeply, because the form holds one object for every field it has.
watch(values, schedulePreview, { deep: true })

onBeforeUnmount(forgetPreview)

function close() {
  emit("update:command", null)
}

async function submit() {
  const command = props.command
  if (!command) return
  if (command.takesFile && !file.value) {
    failure.value = "Choose a file first"
    return
  }

  failure.value = ""
  try {
    const outcome = await runAction.mutateAsync({
      connectorId: props.connectorId,
      name: command.name,
      nodeIds: props.nodeIds,
      params: { ...values.value },
      file: file.value,
    })
    // One line whatever the size of the set: what was done, and what was
    // refused by whom. A refusal in the middle does not stop the rest.
    const said = summarize(outcome, command.label)
    if (outcome.failures.length > 0) toast.error(said)
    else toast.success(said)
    emit("done", outcome)
    close()
  } catch (cause) {
    const fieldErrors = fieldErrorsFrom(cause)
    if (fieldErrors) {
      applyServerErrors(fieldErrors)
    } else {
      failure.value = messageOf(cause, "The action could not be performed")
    }
  }
}
</script>

<template>
  <WindowDialog
    v-if="command"
    :model-value="open"
    size="sm"
    :title="command.label"
    :subtitle="nodeLabel"
    data-testid="action-dialog"
    @update:model-value="close"
  >
    <AppSection gutter>
      <!-- The warning follows the declared flag, not a list of names kept
           here: an action that destroys something says so itself. -->
      <AppBanner
        v-if="command.destructive"
        tone="warning"
        data-testid="action-warning"
      >
        This cannot be undone.
      </AppBanner>

      <AppBanner
        v-if="failure"
        tone="error"
        data-testid="action-error"
      >
        {{ failure }}
      </AppBanner>

      <AppFileInput
        v-if="command.takesFile"
        v-model="file"
        label="File"
        data-testid="action-file"
      />

      <SchemaFields
        v-if="command.fields.length"
        v-model="values"
        :fields="command.fields"
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
        <ul
          v-if="preview.items.length"
          class="action-dialog__consequences"
        >
          <li
            v-for="item in preview.items"
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
        label="Cancel"
        @click="close"
      />
      <!-- A preview that says the source would refuse turns the button off:
           the answer to "what would happen" was "nothing, and here is why". -->
      <AppButton
        :variant="command.destructive ? 'danger' : 'primary'"
        :label="command.label"
        :loading="runAction.isPending.value"
        :disable="preview?.blocked === true"
        data-testid="action-submit"
        @click="submit"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.action-dialog__consequences {
  margin: 4px 0 0;
  padding-left: 20px;
  max-height: 180px;
  overflow: auto;
}
</style>
