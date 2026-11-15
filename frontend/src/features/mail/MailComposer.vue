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

import { useSendMessage } from "./api"
import type { Draft } from "./letter"
import { isAddress, parseAddresses } from "./letter"

/**
 * One letter being written, in a window of its own (D370): several can be
 * open at once beside the mailbox, each with its own draft.
 */
const props = defineProps<{
  connectorId: string
  title: string
  initial: Draft
}>()
const emit = defineEmits<{ closed: [] }>()

const MAX_BYTES = 25 * 1024 * 1024

const open = ref(true)
const draft = ref<Draft>({ ...props.initial })
const files = ref<File[]>([])
const showCopies = ref(props.initial.cc !== "" || props.initial.bcc !== "")

const send = useSendMessage(computed(() => props.connectorId))
const toast = useToast()
const confirm = useConfirm()

const total = computed(() => files.value.reduce((sum, file) => sum + file.size, 0))

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
const blocked = computed(
  () =>
    noRecipient.value ||
    Boolean(toProblem.value || ccProblem.value || bccProblem.value || sizeProblem.value)
)

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
  if (!touched.value || send.isSuccess.value) return true
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

async function submit() {
  if (blocked.value || send.isPending.value) return
  try {
    const sent = await send.mutateAsync({ draft: draft.value, files: files.value })
    toast.success(sent.kept_copy ? t("mail.composer.sent") : t("mail.composer.sent_no_copy"))
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
      <p
        v-if="draft.forward_of"
        class="mail-composer__note"
      >
        {{ t("mail.composer.forwards_files") }}
      </p>
      <AppFileInput
        v-model="files"
        :label="t('mail.composer.attach')"
        multiple
        append
        listed
        data-testid="mail-files"
      />
      <p
        v-if="sizeProblem"
        class="mail-composer__problem"
        role="alert"
      >
        {{ sizeProblem }}
      </p>
      <ul
        v-if="files.length > 0"
        class="mail-composer__files"
      >
        <li
          v-for="(file, index) in files"
          :key="`${file.name}:${index}`"
        >
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
        :label="t('mail.composer.send')"
        :icon="appIcons.send"
        :disable="blocked"
        :loading="send.isPending.value"
        data-testid="mail-send"
        @click="submit"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.mail-composer__text :deep(textarea) {
  min-height: calc(var(--dp-row-height) * 8);
}

.mail-composer__note {
  margin: 0;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
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
