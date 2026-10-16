<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import type { ChatProjectPublic, ConversationSummary, QuickChatSummary } from "@/client"
import { t } from "@/shared/i18n"
import { AppButton, AppIconButton, AppMenu, AppTooltip, toneFill } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

import { chatStateOf, chatStateWords } from "./chatState"
import type { ChatState } from "./chatState"

const props = defineProps<{
  chat: ConversationSummary | QuickChatSummary
  active: boolean
  projects: ChatProjectPublic[]
}>()
const emit = defineEmits<{
  select: []
  pin: [pinned: boolean]
  archive: []
  move: [projectId: string | null]
  newProject: []
}>()

// The buttons are revealed by the pointer, which leaves the row for the menu.
const moving = ref(false)

const NEW_PROJECT = "new-project"
const NO_PROJECT = "no-project"

/** Where this chat can go: another folder, out of the one it is in, or a new one. */
const moves = computed<MenuItem[]>(() => [
  ...props.projects
    .filter((project) => project.id !== props.chat.project_id)
    .map((project) => ({ name: project.id, label: project.name, icon: appIcons.folder })),
  ...(props.chat.project_id
    ? [{ name: NO_PROJECT, label: t("ai.row.no_project"), icon: appIcons.folderOff }]
    : []),
  { name: NEW_PROJECT, label: t("ai.row.new_project"), icon: appIcons.createNewFolder },
])

const state = computed(() => chatStateOf(props.chat))
// The name in full, as a cut one needs, and what the dot says under it.
const stateWords = computed(() => chatStateWords(state.value))
const LOOK: Record<ChatState, string> = {
  idle: "ai-chat-row__state--idle",
  working: "ai-chat-row__state--working",
  waiting: toneFill("warning"),
  failed: toneFill("error"),
}

function pick(name: string) {
  if (name === NEW_PROJECT) emit("newProject")
  else emit("move", name === NO_PROJECT ? null : name)
}
</script>

<template>
  <div
    class="ai-chat-row"
    :class="{ 'ai-chat-row--active': active, 'ai-chat-row--menu': moving }"
    :data-testid="`ai-chat-row-${chat.id}`"
    :data-active="active ? 'true' : 'false'"
  >
    <AppButton
      variant="quiet"
      layout="navigation"
      class="ai-chat-row__title"
      :label="chat.title"
      :aria-description="stateWords ?? undefined"
      :data-testid="`ai-chat-${chat.id}`"
      @click="emit('select')"
    >
      <!-- In the button, so pressing the dot opens the chat too; its words
           are the hover text, and the button's description. -->
      <span
        class="ai-chat-row__state"
        :class="LOOK[state]"
        :data-testid="`ai-chat-state-${chat.id}`"
        :data-state="state"
        aria-hidden="true"
      />
      <AppTooltip>
        <div>{{ chat.title }}</div>
        <div v-if="stateWords">
          {{ stateWords }}
        </div>
      </AppTooltip>
    </AppButton>
    <span class="ai-chat-row__actions">
      <!-- Not in a project: pinned chats are a folder of their own. -->
      <AppIconButton
        v-if="!chat.project_id"
        :icon="appIcons.pushPin"
        :tooltip="chat.pinned ? t('ai.row.unpin') : t('ai.row.pin')"
        :active="chat.pinned"
        compact
        :data-testid="`ai-pin-${chat.id}`"
        @click="emit('pin', !chat.pinned)"
      />
      <span>
        <AppIconButton
          :icon="appIcons.folder"
          :tooltip="t('ai.row.move')"
          compact
          :data-testid="`ai-move-${chat.id}`"
        />
        <AppMenu
          v-model="moving"
          :items="moves"
          @select="pick"
        />
      </span>
      <AppIconButton
        :icon="appIcons.archive"
        :tooltip="t('ai.row.archive')"
        compact
        :data-testid="`ai-archive-${chat.id}`"
        @click="emit('archive')"
      />
    </span>
  </div>
</template>

<style scoped>
/* Like a connection's row (ConnectorList): edge to edge and square, one row
   tall — not a rounded entry inset by the history's padding. */
.ai-chat-row { display: flex; align-items: center; border-radius: 0; min-height: var(--dp-row-height); }
.ai-chat-row:hover,
.ai-chat-row:has(:focus-visible),
.ai-chat-row--menu { background: var(--dp-hover); }
/* The chat on screen is the current page of the list, marked as a tab is (D186). */
.ai-chat-row--active { background: var(--dp-tab-current); }
.ai-chat-row--active > .ai-chat-row__title { font-weight: 500; }
.ai-chat-row > :first-child { flex: 1; min-width: 0; }
/* QBtn puts its slot after the label; the dot stands before it. */
.ai-chat-row__state {
  order: -1;
  flex: none;
  width: 8px;
  height: 8px;
  margin-right: var(--dp-space-2);
  border-radius: 50%;
  box-sizing: border-box;
}
.ai-chat-row__state--idle { border: 1px solid var(--dp-text-muted); }
.ai-chat-row__state--working {
  background: var(--dp-text-muted);
  animation: ai-chat-working 1.2s ease-in-out infinite;
}
@keyframes ai-chat-working {
  50% { opacity: 0.35; transform: scale(0.7); }
}
@media (prefers-reduced-motion: reduce) {
  .ai-chat-row__state--working { animation: none; }
}
/* Quasar's focus helper shades the title button separately from its row. */
.ai-chat-row__title :deep(.q-focus-helper) { display: none; }
.ai-chat-row__actions { display: none; flex: none; }
/* Pointed at, or reached by keyboard, and nothing else: the row of a selected
   chat carries no buttons either.
   Trap: display:none drops the buttons from the accessibility tree, so the
   keyboard half is what keeps them reachable without a mouse at all. It is
   :focus-visible and not :focus-within, because a clicked title keeps focus
   and held the buttons out after the pointer had left. */
.ai-chat-row:hover .ai-chat-row__actions,
.ai-chat-row:has(:focus-visible) .ai-chat-row__actions,
.ai-chat-row--menu .ai-chat-row__actions { display: flex; }
</style>
