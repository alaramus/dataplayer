<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { MailMessage } from "@/client"
import { formatSize } from "@/features/catalog/nodes"
import { t } from "@/shared/i18n"
import { formatDateTime } from "@/shared/i18n/format"
import { AppButton, AppIconButton, AppMenu, appIcons } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

import type { AnswerKind } from "./letter"
import { addressText, letterDocument } from "./letter"

/** One open letter: its headings, its commands, its text and its files (D369). */
const props = defineProps<{
  message: MailMessage
  /** Whether it lies in Trash, where Delete is for good. */
  inTrash: boolean
  busy: boolean
  /** Where it may be moved: the mailbox's folders but its own (D376). */
  targets: { id: string; label: string }[]
}>()
const emit = defineEmits<{
  answer: [kind: AnswerKind]
  edit: []
  move: [target: string]
  delete: []
  unread: []
  download: [part: string, filename: string]
  keep: [part: string]
}>()

// Asked for per letter: a second letter from the same sender is a second
// chance to be told it was read (D369).
const showRemote = ref(false)
watch(
  () => `${props.message.folder}:${props.message.uid}`,
  () => {
    showRemote.value = false
  }
)

const document = computed(() =>
  props.message.html === null
    ? null
    : letterDocument(props.message.html, props.message.inline_images, showRemote.value)
)
const files = computed(() => props.message.attachments)
const sender = computed(() =>
  props.message.sender === null ? t("mail.nobody") : addressText(props.message.sender)
)
const recipients = computed(() => props.message.to.map(addressText).join(", "))
const moving = ref(false)
const moves = computed<MenuItem[]>(() =>
  props.targets.map((one) => ({ name: one.id, label: one.label, icon: appIcons.folder }))
)
const copies = computed(() => props.message.cc.map(addressText).join(", "))
</script>

<template>
  <article
    class="mail-reader"
    data-testid="mail-reader"
  >
    <header class="mail-reader__head">
      <div class="mail-reader__commands">
        <AppButton
          v-if="message.draft"
          layout="toolbar"
          size="sm"
          :icon="appIcons.edit"
          :label="t('mail.edit_draft')"
          data-testid="mail-edit-draft"
          @click="emit('edit')"
        />
        <template v-else>
          <AppButton
            variant="secondary"
            layout="toolbar"
            size="sm"
            :icon="appIcons.reply"
            :label="t('mail.reply')"
            data-testid="mail-reply"
            @click="emit('answer', 'reply')"
          />
          <AppButton
            variant="quiet"
            layout="toolbar"
            size="sm"
            :icon="appIcons.replyAll"
            :label="t('mail.reply_all')"
            data-testid="mail-reply-all"
            @click="emit('answer', 'reply_all')"
          />
          <AppButton
            variant="quiet"
            layout="toolbar"
            size="sm"
            :icon="appIcons.forward"
            :label="t('mail.forward')"
            data-testid="mail-forward"
            @click="emit('answer', 'forward')"
          />
        </template>
        <span class="mail-reader__spacer" />
        <span>
          <AppIconButton
            :icon="appIcons.moveToFolder"
            :tooltip="t('mail.move_to')"
            :disable="busy || targets.length === 0"
            data-testid="mail-move"
          />
          <AppMenu
            v-model="moving"
            :items="moves"
            @select="(target: string) => emit('move', target)"
          />
        </span>
        <AppIconButton
          :icon="appIcons.markUnread"
          :tooltip="t('mail.mark_unread')"
          :disable="busy"
          data-testid="mail-mark-unread"
          @click="emit('unread')"
        />
        <AppIconButton
          :icon="inTrash ? appIcons.deleteForever : appIcons.delete"
          :tooltip="t('mail.delete')"
          variant="danger-quiet"
          :disable="busy"
          data-testid="mail-delete"
          @click="emit('delete')"
        />
      </div>
      <h2 class="mail-reader__subject">
        {{ message.subject || t("mail.no_subject") }}
      </h2>
      <dl class="mail-reader__fields">
        <dt>{{ t("mail.from") }}</dt>
        <dd data-testid="mail-reader-from">
          {{ sender }}
        </dd>
        <dt>{{ t("mail.to") }}</dt>
        <dd>{{ recipients || t("mail.nobody") }}</dd>
        <template v-if="copies">
          <dt>{{ t("mail.cc") }}</dt>
          <dd>{{ copies }}</dd>
        </template>
        <template v-if="message.date">
          <dt />
          <dd class="mail-reader__date">
            {{ formatDateTime(message.date) }}
          </dd>
        </template>
      </dl>
      <ul
        v-if="files.length > 0"
        class="mail-reader__files"
        :aria-label="t('mail.attachments')"
      >
        <li
          v-for="file in files"
          :key="file.part"
          class="mail-reader__file"
          data-testid="mail-attachment"
        >
          <q-icon
            :name="appIcons.attachFile"
            size="var(--dp-icon-sm)"
          />
          <span class="mail-reader__file-name">{{ file.filename }}</span>
          <span class="mail-reader__file-size">{{ formatSize(file.size) }}</span>
          <AppIconButton
            :icon="appIcons.download"
            :tooltip="t('mail.download')"
            data-testid="mail-attachment-download"
            @click="emit('download', file.part, file.filename)"
          />
          <AppIconButton
            :icon="appIcons.createNewFolder"
            :tooltip="t('mail.keep')"
            data-testid="mail-attachment-keep"
            @click="emit('keep', file.part)"
          />
        </li>
      </ul>
      <div
        v-if="document && document.blockedImages > 0"
        class="mail-reader__images"
      >
        <span>{{ t("mail.images_blocked") }}</span>
        <AppButton
          variant="quiet"
          size="sm"
          :icon="appIcons.image"
          :label="t('mail.show_images')"
          data-testid="mail-show-images"
          @click="showRemote = true"
        />
      </div>
    </header>
    <!-- No scripts, no forms, nothing that navigates this page; a link opens a
         tab of its own (D369). -->
    <iframe
      v-if="document"
      class="mail-reader__body"
      sandbox="allow-popups allow-popups-to-escape-sandbox"
      referrerpolicy="no-referrer"
      :title="message.subject || t('mail.no_subject')"
      :srcdoc="document.srcdoc"
      data-testid="mail-html"
    />
    <pre
      v-else-if="message.text"
      class="mail-reader__text"
      data-testid="mail-text-body"
    >{{ message.text }}</pre>
    <p
      v-else
      class="mail-reader__none"
    >
      {{ t("mail.no_text") }}
    </p>
  </article>
</template>

<style scoped>
.mail-reader {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.mail-reader__head {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-3);
  border-bottom: 1px solid var(--dp-border-faint);
}

.mail-reader__commands {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
}

.mail-reader__spacer {
  flex: 1;
}

.mail-reader__subject {
  margin: 0;
  font-size: var(--dp-font-size-lg);
  line-height: var(--dp-line-height);
  overflow-wrap: anywhere;
}

.mail-reader__fields {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--dp-space-half) var(--dp-space-2);
  margin: 0;
  font-size: var(--dp-font-size-sm);
}

.mail-reader__fields dt {
  color: var(--dp-text-muted);
}

.mail-reader__fields dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.mail-reader__date {
  color: var(--dp-text-muted);
}

.mail-reader__files {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-1) var(--dp-space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.mail-reader__file {
  display: flex;
  align-items: center;
  gap: var(--dp-space-1);
  max-width: 100%;
}

.mail-reader__file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mail-reader__file-size {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}

.mail-reader__images {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}

.mail-reader__body {
  flex: 1;
  width: 100%;
  min-height: 0;
  border: 0;
}

.mail-reader__text {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: var(--dp-space-3);
  overflow: auto;
  font-family: var(--dp-font-ui);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.mail-reader__none {
  padding: var(--dp-space-3);
  color: var(--dp-text-muted);
}
</style>
