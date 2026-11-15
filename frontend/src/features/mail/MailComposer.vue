<script setup lang="ts">
import { computed, ref } from "vue"

import { formatSize } from "@/features/catalog/nodes"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppButton,
  AppFileInput,
  AppForm,
  AppIconButton,
  AppInput,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useSaveDraft, useSendMessage } from "./api"
import type { Draft, StoredFile } from "./letter"
import { isAddress, parseAddresses } from "./letter"
import MyFilesDialog from "./MyFilesDialog.vue"

/**
 * One letter being written, in a window of its own (D370): several can be
 * open at once beside the mailbox, each with its own draft.
 */
const props = defineProps<{
  connectorId: string
  title: string
  initial: Draft
}>()
const emit = defineEmits<{
  closed: []
  /** The draft it was finishing is gone: sent, or replaced by a new one (D375). */
  replaced: [draft: { folder: string; uid: number }]
}>()

const MAX_BYTES = 25 * 1024 * 1024

const open = ref(true)
const draft = ref<Draft>({ ...props.initial })
const files = ref<File[]>([])
const showCopies = ref(props.initial.cc !== "" || props.initial.bcc !== "")

const send = useSendMessage(computed(() => props.connectorId))
const saveDraft = useSaveDraft(computed(() => props.connectorId))
const picking = ref(false)
const toast = useToast()
const confirm = useConfirm()

const total = computed(
  () =>
    files.value.reduce((sum, file) => sum + file.size, 0) +
    draft.value.carried.reduce((sum, one) => sum + one.size, 0) +
    draft.value.stored.reduce((sum, one) => sum + one.size, 0)
)
const attachedCount = computed(
  () => files.value.length + draft.value.carried.length + draft.value.stored.length
)

function wrongAddress(text: string): string {
  const bad = parseAddresses(text).find((one) => !isAddress(one))
  return bad === undefined ? "" : t("mail.composer.bad_address", { address: bad })
}

const toProblem = computed(() =>
  draft.value.to.trim() === "" ? "" : wrongAddress(draft.value.to)
)
const ccProblem = computed(() => wrongAddress(draft.value.cc))
const bccProblem = computed(() => wrongAddress(draft.value.bcc))
const sizeProblem = computed(() => (total.value > MAX_BYTES ? t("mail.composer.too_large") : ""))
const noRecipient = computed(() => parseAddresses(draft.value.to).length === 0)
const wrong = computed(() =>
  Boolean(toProblem.value || ccProblem.value || bccProblem.value || sizeProblem.value)
)
const blocked = computed(() => noRecipient.value || wrong.value)
// A draft may have nobody to go to yet (D375).
const draftBlocked = computed(() => wrong.value)
const busy = computed(() => send.isPending.value || saveDraft.isPending.value)

const touched = computed(
  () =>
    files.value.length > 0 ||
    (Object.keys(props.initial) as (keyof Draft)[]).some(
      (key) => draft.value[key] !== props.initial[key]
    )
)

function close() {
  open.value = false
  emit("closed")
}

async function mayClose(): Promise<boolean> {
  if (!touched.value || send.isSuccess.value || saveDraft.isSuccess.value) return true
  return confirm({
    title: t("mail.composer.discard.title"),
    message: t("mail.composer.discard.message"),
    confirmLabel: t("mail.composer.discard.confirm"),
    danger: true,
  })
}

async function cancel() {
  if (await mayClose()) close()
}

function removeFile(index: number) {
  files.value = files.value.filter((_, at) => at !== index)
}

function removeCarried(part: string) {
  draft.value = { ...draft.value, carried: draft.value.carried.filter((one) => one.part !== part) }
}

function removeStored(path: string) {
  draft.value = { ...draft.value, stored: draft.value.stored.filter((one) => one.path !== path) }
}

function addStored(chosen: StoredFile[]) {
  const known = new Set(draft.value.stored.map((one) => one.path))
  draft.value = {
    ...draft.value,
    stored: [...draft.value.stored, ...chosen.filter((one) => !known.has(one.path))],
  }
}

/** Into Drafts; the window closes, and the draft opens again from Drafts (D375). */
async function keepDraft() {
  if (draftBlocked.value || busy.value) return
  try {
    const saved = await saveDraft.mutateAsync({ draft: draft.value, files: files.value })
    toast.success(t("mail.composer.draft_saved", { folder: saved.folder }))
    if (draft.value.draft_of !== null) emit("replaced", draft.value.draft_of)
    close()
  } catch (cause) {
    toast.error(messageOf(cause, t("mail.composer.could_not_save")))
  }
}

async function submit() {
  if (blocked.value || busy.value) return
  try {
    const sent = await send.mutateAsync({ draft: draft.value, files: files.value })
    toast.success(sent.kept_copy ? t("mail.composer.sent") : t("mail.composer.sent_no_copy"))
    if (draft.value.draft_of !== null) emit("replaced", draft.value.draft_of)
    close()
  } catch (cause) {
    toast.error(messageOf(cause, t("mail.composer.could_not_send")))
  }
}
</script>

<template>
  <WindowDialog
    :model-value="open"
    :title="title"
    size="wide-form"
    sizing="stable"
    :before-close="mayClose"
    data-testid="mail-composer"
    @update:model-value="(value) => { if (!value) close() }"
  >
    <AppForm
      layout="section"
      labels="above"
      class="mail-composer"
    >
      <AppInput
        v-model="draft.to"
        :label="t('mail.to')"
        :hint="t('mail.composer.to_hint')"
        :error="toProblem"
        autofocus
        data-testid="mail-to"
      >
        <template #after>
          <AppButton
            v-if="!showCopies"
            variant="quiet"
            size="sm"
            :label="`${t('mail.cc')} / ${t('mail.bcc')}`"
            data-testid="mail-show-copies"
            @click="showCopies = true"
          />
        </template>
      </AppInput>
      <template v-if="showCopies">
        <AppInput
          v-model="draft.cc"
          :label="t('mail.cc')"
          :error="ccProblem"
          data-testid="mail-cc"
        />
        <AppInput
          v-model="draft.bcc"
          :label="t('mail.bcc')"
          :error="bccProblem"
          data-testid="mail-bcc"
        />
      </template>
      <AppInput
        v-model="draft.subject"
        :label="t('mail.subject')"
        data-testid="mail-subject"
      />
      <AppInput
        v-model="draft.text"
        type="textarea"
        class="mail-composer__text"
        data-testid="mail-text"
      />
      <!-- The second way to attach beside the field, where To keeps Cc and
           Bcc: one line, the button centred on the box rather than on the
           box and its label together. -->
      <AppFileInput
        v-model="files"
        class="mail-composer__attach"
        :label="t('mail.composer.attach')"
        multiple
        append
        listed
        data-testid="mail-files"
      >
        <template #after>
          <AppButton
            variant="secondary"
            :icon="appIcons.folder"
            :label="t('mail.composer.from_my_folder')"
            data-testid="mail-from-my-folder"
            @click="picking = true"
          />
        </template>
      </AppFileInput>
      <p
        v-if="sizeProblem"
        class="mail-composer__problem"
        role="alert"
      >
        {{ sizeProblem }}
      </p>
      <ul
        v-if="attachedCount > 0"
        class="mail-composer__files"
        data-testid="mail-attached"
      >
        <li
          v-for="one in draft.carried"
          :key="`carried:${one.part}`"
        >
          <q-icon
            :name="appIcons.attachFile"
            size="var(--dp-icon-sm)"
          />
          <span class="mail-composer__file-name">{{ one.filename }}</span>
          <span class="mail-composer__file-size">{{ formatSize(one.size) }}</span>
          <AppIconButton
            :icon="appIcons.close"
            :tooltip="t('mail.composer.remove_file', { name: one.filename })"
            @click="removeCarried(one.part)"
          />
        </li>
        <li
          v-for="one in draft.stored"
          :key="`stored:${one.path}`"
        >
          <q-icon
            :name="appIcons.folder"
            size="var(--dp-icon-sm)"
          />
          <span
            class="mail-composer__file-name"
            :title="one.path"
          >{{ one.name }}</span>
          <span class="mail-composer__file-size">{{ formatSize(one.size) }}</span>
          <AppIconButton
            :icon="appIcons.close"
            :tooltip="t('mail.composer.remove_file', { name: one.name })"
            @click="removeStored(one.path)"
          />
        </li>
        <li
          v-for="(file, index) in files"
          :key="`upload:${file.name}:${index}`"
        >
          <q-icon
            :name="appIcons.importSshKey"
            size="var(--dp-icon-sm)"
          />
          <span class="mail-composer__file-name">{{ file.name }}</span>
          <span class="mail-composer__file-size">{{ formatSize(file.size) }}</span>
          <AppIconButton
            :icon="appIcons.close"
            :tooltip="t('mail.composer.remove_file', { name: file.name })"
            @click="removeFile(index)"
          />
        </li>
      </ul>
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('mail.composer.cancel')"
        @click="cancel"
      />
      <AppButton
        variant="secondary"
        :label="t('mail.composer.save_draft')"
        :icon="appIcons.save"
        :disable="draftBlocked || busy"
        :loading="saveDraft.isPending.value"
        data-testid="mail-save-draft"
        @click="keepDraft"
      />
      <AppButton
        :label="t('mail.composer.send')"
        :icon="appIcons.send"
        :disable="blocked || busy"
        :loading="send.isPending.value"
        data-testid="mail-send"
        @click="submit"
      />
    </template>
  </WindowDialog>
  <MyFilesDialog
    v-if="picking"
    v-model="picking"
    :connector-id="connectorId"
    @add="addStored"
  />
</template>

<style scoped>
.mail-composer__text :deep(textarea) {
  min-height: calc(var(--dp-row-height) * 8);
}

.mail-composer__attach {
  max-width: var(--dp-width-text);
}

.mail-composer__problem {
  margin: 0;
  color: var(--dp-content-error);
  font-size: var(--dp-font-size-sm);
}

.mail-composer__files {
  margin: 0;
  padding: 0;
  list-style: none;
}

.mail-composer__files li {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
}

.mail-composer__file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mail-composer__file-size {
  flex: 1;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
</style>
