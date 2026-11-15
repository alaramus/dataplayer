<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { MessageHeading } from "@/client"
import { useConnectors } from "@/features/connectors/api"
import SourceErrorBanner from "@/features/sshKeys/SourceErrorBanner.vue"
import PanelCommands from "@/features/workspace/PanelCommands.vue"
import { useReloadable } from "@/features/workspace/reloadable"
import { errorKindOf, messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { formatDate, formatTime } from "@/shared/i18n/format"
import {
  AppBadge,
  AppButton,
  AppEmptyState,
  AppIconButton,
  AppInput,
  AppSpinner,
  appIcons,
  useConfirm,
  useToast,
} from "@/shared/ui"

import {
  PAGE_SIZE,
  useDeleteMessages,
  useDownloadAttachment,
  useKeepAttachment,
  useMailFolders,
  useMailMessage,
  useMailPage,
  useMarkMessages,
  useMoveMessages,
} from "./api"
import type { MessageRef } from "./api"
import { firstFolder, shownFolders } from "./folders"
import type { AnswerKind, Draft } from "./letter"
import { addressText, answerDraft, draftFrom, emptyDraft } from "./letter"
import MailComposer from "./MailComposer.vue"
import MailReader from "./MailReader.vue"

/**
 * A mailbox opened as a mail client, in place of a catalog (D366): folders,
 * the letters of one, and the letter being read.
 */
const props = defineProps<{
  panelId: string
  connectorId: string
  title: string
}>()

const connectorId = computed(() => props.connectorId)
const folder = ref<string | null>(null)
const offset = ref(0)
const searchText = ref("")
const search = ref("")
const selected = ref<MessageRef | null>(null)

const folders = useMailFolders(connectorId)
const page = useMailPage(connectorId, folder, offset, search)
const message = useMailMessage(connectorId, selected)
const mark = useMarkMessages(connectorId)
const move = useMoveMessages(connectorId)
const remove = useDeleteMessages(connectorId)
const download = useDownloadAttachment(connectorId)
const keep = useKeepAttachment(connectorId)
const toast = useToast()
const confirm = useConfirm()

watch(
  () => folders.data.value,
  (found) => {
    if (found === undefined) return
    if (folder.value === null || !found.some((one) => one.id === folder.value)) {
      folder.value = firstFolder(found)
    }
  },
  { immediate: true }
)

const shown = computed(() =>
  shownFolders(folders.data.value ?? [], (role) => t(`mail.roles.${role}`))
)
const current = computed(() => shown.value.find((one) => one.id === folder.value) ?? null)
const inTrash = computed(() => current.value?.role === "trash")
const targets = computed(() =>
  shown.value
    .filter((one) => one.selectable && one.id !== folder.value)
    .map((one) => ({ id: one.id, label: one.label }))
)
const headings = computed(() => page.data.value?.messages ?? [])
const total = computed(() => page.data.value?.total ?? 0)

const failure = computed(() => folders.error.value ?? page.error.value)
const failureText = computed(() =>
  failure.value ? messageOf(failure.value, t("mail.could_not_read")) : ""
)

function openFolder(id: string) {
  if (folder.value === id) return
  folder.value = id
  offset.value = 0
  search.value = ""
  searchText.value = ""
  selected.value = null
}

function runSearch() {
  search.value = searchText.value.trim()
  offset.value = 0
}

function clearSearch() {
  searchText.value = ""
  runSearch()
}

function open(heading: MessageHeading) {
  if (folder.value === null) return
  selected.value = { folder: folder.value, uid: heading.uid }
}

function isOpen(heading: MessageHeading): boolean {
  return selected.value?.uid === heading.uid && selected.value.folder === folder.value
}

function when(date: string | null | undefined): string {
  if (!date) return ""
  const moment = new Date(date)
  const today = new Date()
  return moment.toDateString() === today.toDateString() ? formatTime(moment, { hour: "2-digit", minute: "2-digit" }) : formatDate(moment)
}

const range = computed(() =>
  total.value === 0
    ? ""
    : t("mail.range", {
        from: offset.value + 1,
        to: Math.min(offset.value + PAGE_SIZE, total.value),
        total: total.value,
      })
)

async function reload() {
  await Promise.all([folders.refetch(), page.refetch()])
}

useReloadable(() => props.panelId, reload)

// --- commands on the open letter -------------------------------------------

async function deleteOpen() {
  const chosen = selected.value
  if (chosen === null) return
  if (inTrash.value) {
    const sure = await confirm({
      title: t("mail.delete_forever.title"),
      message: t("mail.delete_forever.message"),
      confirmLabel: t("mail.delete_forever.confirm"),
      danger: true,
    })
    if (!sure) return
  }
  try {
    const done = await remove.mutateAsync({ folder: chosen.folder, uids: [chosen.uid] })
    toast.success(done.moved_to === null ? t("mail.deleted") : t("mail.moved_to_trash"))
    selected.value = null
  } catch (cause) {
    toast.error(messageOf(cause, t("mail.could_not_do")))
  }
}

async function moveOpen(target: string) {
  const chosen = selected.value
  if (chosen === null) return
  try {
    await move.mutateAsync({ folder: chosen.folder, uids: [chosen.uid], target })
    const label = shown.value.find((one) => one.id === target)?.label ?? target
    toast.success(t("mail.moved", { folder: label }))
    selected.value = null
  } catch (cause) {
    toast.error(messageOf(cause, t("mail.could_not_do")))
  }
}

function editDraft() {
  const letter = message.data.value
  if (letter === undefined) return
  write(t("mail.composer.draft"), draftFrom(letter))
}

async function markUnread() {
  const chosen = selected.value
  if (chosen === null) return
  try {
    await mark.mutateAsync({ folder: chosen.folder, uids: [chosen.uid], seen: false })
    selected.value = null
  } catch (cause) {
    toast.error(messageOf(cause, t("mail.could_not_do")))
  }
}

async function downloadFile(part: string, filename: string) {
  const chosen = selected.value
  if (chosen === null) return
  try {
    await download.mutateAsync({ ...chosen, part, filename })
  } catch (cause) {
    toast.error(messageOf(cause, t("mail.could_not_do")))
  }
}

async function keepFile(part: string) {
  const chosen = selected.value
  if (chosen === null) return
  try {
    const kept = await keep.mutateAsync({ ...chosen, part })
    toast.success(t("mail.kept", { path: kept.path }))
  } catch (cause) {
    toast.error(messageOf(cause, t("mail.could_not_do")))
  }
}

// --- letters being written -------------------------------------------------

interface Composer {
  key: number
  title: string
  draft: Draft
}

const composers = ref<Composer[]>([])
let composed = 0

function write(title: string, draft: Draft) {
  composed += 1
  composers.value = [...composers.value, { key: composed, title, draft }]
}

function newLetter() {
  write(t("mail.composer.new"), emptyDraft())
}

function answer(kind: AnswerKind) {
  const letter = message.data.value
  if (letter === undefined) return
  const who = letter.sender === null ? t("mail.nobody") : addressText(letter.sender)
  const date = letter.date ? formatDate(letter.date) : ""
  const draft = answerDraft(kind, letter, mailboxAddress.value, {
    wrote: date ? t("mail.wrote", { who, date }) : t("mail.wrote_undated", { who }),
    forwarded: t("mail.forwarded", {
      from: who,
      date,
      subject: letter.subject,
      to: letter.to.map(addressText).join(", "),
    }),
  })
  write(kind === "forward" ? t("mail.composer.forward") : t("mail.composer.reply"), draft)
}

/** A draft that was sent or saved anew is no longer there to be read. */
function forgetDraft(draft: MessageRef) {
  if (selected.value?.folder === draft.folder && selected.value.uid === draft.uid) {
    selected.value = null
  }
}

function closed(key: number) {
  composers.value = composers.value.filter((one) => one.key !== key)
}

/** The mailbox's own address, left out of Reply all: a non-secret option. */
const connectors = useConnectors()
const mailboxAddress = computed(() => {
  const config = connectors.data.value?.data.find((one) => one.id === props.connectorId)?.config
  const address = config?.["address"]
  return typeof address === "string" ? address : ""
})
</script>

<template>
  <div
    class="mail"
    data-testid="mail-panel"
  >
    <div class="mail__bar">
      <AppButton
        :icon="appIcons.editSquare"
        :label="t('mail.new_letter')"
        layout="toolbar"
        size="sm"
        data-testid="mail-new"
        @click="newLetter"
      />
      <AppInput
        v-model="searchText"
        class="mail__search"
        :label="t('mail.search')"
        :placeholder="t('mail.search_hint')"
        compact
        data-testid="mail-search"
        @keydown.enter.prevent="runSearch"
      >
        <template #prepend>
          <q-icon :name="appIcons.search" />
        </template>
      </AppInput>
      <AppIconButton
        v-if="search"
        :icon="appIcons.close"
        :tooltip="t('mail.clear_search')"
        @click="clearSearch"
      />
      <span class="mail__range">{{ range }}</span>
      <AppIconButton
        :icon="appIcons.chevronLeft"
        :tooltip="t('mail.newer')"
        :disable="offset === 0"
        data-testid="mail-newer"
        @click="offset = Math.max(0, offset - PAGE_SIZE)"
      />
      <AppIconButton
        :icon="appIcons.chevronRight"
        :tooltip="t('mail.older')"
        :disable="offset + PAGE_SIZE >= total"
        data-testid="mail-older"
        @click="offset += PAGE_SIZE"
      />
      <PanelCommands :panel-id="panelId" />
    </div>
    <SourceErrorBanner
      v-if="failureText"
      :error-kind="errorKindOf(failure)"
      :connector-id="connectorId"
      @unlocked="reload"
    >
      {{ failureText }}
    </SourceErrorBanner>
    <div class="mail__body">
      <nav
        class="mail__folders"
        :aria-label="t('mail.folders')"
      >
        <AppSpinner v-if="folders.isLoading.value" />
        <AppButton
          v-for="one in shown"
          :key="one.id"
          :variant="one.id === folder ? 'current' : 'quiet'"
          layout="navigation"
          :label="one.label"
          :disable="!one.selectable"
          :style="{ paddingInlineStart: `calc(var(--dp-space-2) + var(--dp-space-3) * ${one.depth})` }"
          :data-testid="`mail-folder-${one.role ?? 'other'}`"
          @click="openFolder(one.id)"
        >
          <AppBadge
            v-if="one.unseen > 0"
            :label="String(one.unseen)"
            :aria-label="t('mail.unread', { n: one.unseen })"
          />
        </AppButton>
      </nav>
      <section
        class="mail__list"
        data-testid="mail-list"
      >
        <AppSpinner v-if="page.isLoading.value" />
        <AppEmptyState
          v-else-if="!failure && headings.length === 0 && folder !== null"
          :text="search ? t('mail.nothing_found') : t('mail.empty_folder')"
          :icon="appIcons.inbox"
          inset
        />
        <button
          v-for="heading in headings"
          :key="heading.uid"
          type="button"
          class="mail__row"
          :class="{ 'mail__row--unread': !heading.seen, 'mail__row--open': isOpen(heading) }"
          :aria-current="isOpen(heading) ? 'true' : undefined"
          data-testid="mail-row"
          @click="open(heading)"
        >
          <span class="mail__who">
            {{ heading.sender ? (heading.sender.name || heading.sender.address) : t("mail.nobody") }}
          </span>
          <span class="mail__when">{{ when(heading.date) }}</span>
          <span class="mail__subject">
            <q-icon
              v-if="heading.answered"
              :name="appIcons.reply"
              size="var(--dp-icon-sm)"
              :aria-label="t('mail.answered')"
            />
            <q-icon
              v-if="heading.has_attachments"
              :name="appIcons.attachFile"
              size="var(--dp-icon-sm)"
              :aria-label="t('mail.has_files')"
            />
            {{ heading.subject || t("mail.no_subject") }}
          </span>
        </button>
      </section>
      <section class="mail__reader">
        <AppSpinner v-if="message.isFetching.value && !message.data.value" />
        <p
          v-else-if="message.isError.value"
          class="mail__problem"
        >
          {{ messageOf(message.error.value, t("mail.could_not_open")) }}
        </p>
        <MailReader
          v-else-if="selected && message.data.value"
          :message="message.data.value"
          :in-trash="inTrash"
          :busy="remove.isPending.value || mark.isPending.value || move.isPending.value"
          :targets="targets"
          @answer="answer"
          @edit="editDraft"
          @move="moveOpen"
          @delete="deleteOpen"
          @unread="markUnread"
          @download="downloadFile"
          @keep="keepFile"
        />
        <AppEmptyState
          v-else
          :text="t('mail.choose')"
          :icon="appIcons.mail"
          inset
        />
      </section>
    </div>
    <MailComposer
      v-for="one in composers"
      :key="one.key"
      :connector-id="connectorId"
      :title="one.title"
      :initial="one.draft"
      @closed="closed(one.key)"
      @replaced="forgetDraft"
    />
  </div>
</template>

<style scoped>
.mail {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.mail__bar {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  min-height: var(--dp-toolbar-height);
  padding: 0 var(--dp-space-2);
  border-bottom: 1px solid var(--dp-border-faint);
}

.mail__search {
  flex: 1;
  max-width: var(--dp-width-text);
}

.mail__range {
  margin-inline-start: auto;
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
  white-space: nowrap;
}

.mail__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) minmax(0, 3fr);
  flex: 1;
  min-height: 0;
}

.mail__folders {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-half);
  padding: var(--dp-space-2) var(--dp-space-1);
  overflow-y: auto;
  border-inline-end: 1px solid var(--dp-border-faint);
}

.mail__list {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  border-inline-end: 1px solid var(--dp-border-faint);
}

.mail__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--dp-space-half) var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-3);
  border: 0;
  border-bottom: 1px solid var(--dp-border-faint);
  background: transparent;
  color: var(--dp-text);
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.mail__row:hover {
  background: var(--dp-hover);
}

.mail__row:focus-visible {
  outline: 1px solid var(--dp-focus-border);
  outline-offset: -1px;
}

.mail__row--open {
  background: var(--dp-selected);
}

.mail__row--unread .mail__who,
.mail__row--unread .mail__subject {
  font-weight: 600;
}

.mail__who,
.mail__subject {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mail__subject {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  color: var(--dp-text-muted);
}

.mail__row--unread .mail__subject {
  color: var(--dp-text);
}

.mail__when {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
  white-space: nowrap;
}

.mail__reader {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.mail__problem {
  padding: var(--dp-space-3);
  color: var(--dp-content-error);
}
</style>
