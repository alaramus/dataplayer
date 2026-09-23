<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import type { ChatProjectPublic, ConversationSummary } from "@/client"
import { AppButton, AppIconButton, AppMenu } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

const props = defineProps<{
  chat: ConversationSummary
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
    ? [{ name: NO_PROJECT, label: "No project", icon: appIcons.folderOff }]
    : []),
  { name: NEW_PROJECT, label: "New project…", icon: appIcons.createNewFolder },
])

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
      :title="chat.title"
      :data-testid="`ai-chat-${chat.id}`"
      @click="emit('select')"
    />
    <span class="ai-chat-row__actions">
      <AppIconButton
        :icon="appIcons.pushPin"
        :tooltip="chat.pinned ? 'Unpin chat' : 'Pin chat'"
        :active="chat.pinned"
        compact
        :data-testid="`ai-pin-${chat.id}`"
        @click="emit('pin', !chat.pinned)"
      />
      <span>
        <AppIconButton
          :icon="appIcons.folder"
          tooltip="Move to project"
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
        tooltip="Archive chat"
        compact
        :data-testid="`ai-archive-${chat.id}`"
        @click="emit('archive')"
      />
    </span>
  </div>
</template>

<style scoped>
.ai-chat-row { display: flex; align-items: center; border-radius: var(--dp-radius-control); }
.ai-chat-row--active { background: var(--dp-active); }
.ai-chat-row > :first-child { flex: 1; min-width: 0; }
/* A generated title is a sentence; the row gets one line of it, the rest is
   on the button's tooltip. */
.ai-chat-row__title :deep(.q-btn__content) { display: block; overflow: hidden; text-align: left; text-overflow: ellipsis; white-space: nowrap; }
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
