<script setup lang="ts">
import { computed, ref, watch } from "vue"

import CodeEditor from "@/features/content/CodeEditor.vue"
import { useDownloadAction } from "@/features/catalog/api"
import { drawnBy } from "@/features/catalog/modelCode"
import { messageOf } from "@/shared/api/errors"
import { client } from "@/client/client.gen"
import { copyText } from "@/shared/clipboard"
import { filenameFromDisposition, saveBrowserDownload } from "@/shared/download"
import type { SchemaChoice } from "@/shared/SchemaForm/jsonSchema"
import { AppBanner, AppButton, AppSpinner, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

/**
 * The model of what was selected, read before it is taken anywhere.
 *
 * A screen of its own rather than the generic form, because the answer is a
 * document: it is worth reading, worth copying, and for one dialect worth
 * carrying to a website that draws it. A form has nowhere to put any of that,
 * and downloading a file somebody has not seen is asking them to open it in
 * something else to find out what it says (D73).
 *
 * Three dialects are three buttons, not a select: the whole choice fits on one
 * line, and a menu to pick one of three is a click that buys nothing.
 */
const props = defineProps<{
  modelValue: boolean
  connectorId: string
  nodeIds: string[]
  label: string
  /** The dialects the source offers, in its own words. */
  choices: SchemaChoice[]
  /** The one the source calls the default, when it names one. */
  chosen?: string
}>()

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()

const toast = useToast()
const prepare = useDownloadAction()

const dialect = ref(
  props.chosen !== undefined && props.chosen !== ""
    ? props.chosen
    : (props.choices[0]?.value ?? "")
)
const text = ref("")
const filename = ref("model.txt")
const failure = ref("")
const loading = ref(false)

/** Where this dialect is drawn, when somewhere draws it. */
const drawnAt = computed(() => drawnBy(dialect.value))

/**
 * Ask the source to write it, and read what comes back.
 *
 * Through the same ticket a download follows: one route, one answer, and the
 * bytes are already here when somebody presses Save. The ticket is the
 * authority for the request, so nothing else has to be sent with it.
 */
async function write() {
  const targets = props.nodeIds.filter((id): id is string => id !== null && id !== "")
  if (targets.length === 0) {
    failure.value = "Choose what to describe"
    return
  }
  loading.value = true
  failure.value = ""
  const wanted = dialect.value
  try {
    const ready = await prepare.mutateAsync({
      connectorId: props.connectorId,
      name: "describe_model",
      nodeIds: targets,
      params: { dialect: wanted },
    })
    const answer = await fetch(client.buildUrl({ url: ready.download_url }))
    if (!answer.ok) throw new Error(`The source answered ${String(answer.status)}`)
    const body = await answer.text()
    // A dialect chosen while this was in flight wins: the answer that arrives
    // last is not the answer somebody is looking at.
    if (wanted !== dialect.value) return
    text.value = body
    filename.value = filenameFromDisposition(
      answer.headers.get("content-disposition") ?? undefined,
      "model.txt"
    )
  } catch (cause) {
    if (wanted !== dialect.value) return
    text.value = ""
    failure.value = messageOf(cause, "The model could not be written")
  } finally {
    loading.value = false
  }
}

watch(
  [() => props.modelValue, dialect],
  ([open]) => {
    if (open) void write()
  },
  { immediate: true }
)

async function copy() {
  await copyText(text.value)
  toast.success(`${filename.value} copied`)
}

function save() {
  saveBrowserDownload(
    new Blob([text.value], { type: "text/plain;charset=utf-8" }),
    filename.value
  )
}

/** Open the site that draws this, in a window of its own. */
function visit() {
  const where = drawnAt.value
  if (where === null) return
  window.open(where.url, "_blank", "noopener,noreferrer")
}

function close() {
  emit("update:modelValue", false)
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    size="lg"
    title="Model as code"
    :subtitle="label"
    data-testid="model-code-dialog"
    @update:model-value="close"
  >
    <div class="model-code">
      <!-- Three names on one line. The words are the source's; nothing here
           knows what any of them means. -->
      <div
        class="model-code__dialects"
        data-testid="model-code-dialects"
      >
        <AppButton
          v-for="choice in choices"
          :key="choice.value"
          :variant="choice.value === dialect ? 'secondary' : 'quiet'"
          size="sm"
          :label="choice.label"
          :data-testid="`model-code-dialect-${choice.value}`"
          :data-chosen="choice.value === dialect ? 'yes' : 'no'"
          @click="dialect = choice.value"
        />
      </div>

      <AppBanner
        v-if="failure"
        tone="error"
        data-testid="model-code-error"
      >
        {{ failure }}
      </AppBanner>

      <div
        v-else-if="loading && text === ''"
        class="model-code__waiting"
      >
        <AppSpinner />
      </div>

      <!-- Read-only, and in the editor everything else in this application
           reads code in: the language follows the name of the file the source
           would have saved. -->
      <CodeEditor
        v-else
        class="model-code__text"
        :model-value="text"
        :filename="filename"
        readonly
        data-testid="model-code-text"
      />
    </div>

    <template #actions>
      <!-- Only for a dialect something draws. The file is what the site
           takes, so the door is offered beside Copy and Save rather than
           instead of them. -->
      <AppButton
        v-if="drawnAt"
        variant="quiet"
        icon="open_in_new"
        :label="drawnAt.label"
        data-testid="model-code-site"
        @click="visit"
      />
      <AppButton
        variant="quiet"
        label="Save"
        :disable="text === ''"
        data-testid="model-code-save"
        @click="save"
      />
      <AppButton
        variant="secondary"
        label="Copy"
        :disable="text === ''"
        data-testid="model-code-copy"
        @click="copy"
      />
      <AppButton
        variant="primary"
        label="Close"
        data-testid="model-code-close"
        @click="close"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.model-code {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  min-height: 0;
}

.model-code__dialects {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  flex-wrap: wrap;
}

/* A document, not a field: it takes the height the window can spare and
   scrolls inside itself. */
.model-code__text {
  flex: 1;
  min-height: 320px;
  max-height: 60vh;
  overflow: auto;
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius);
}

.model-code__waiting {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}
</style>
