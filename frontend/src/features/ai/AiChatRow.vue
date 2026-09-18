<script setup lang="ts">
import { computed } from "vue"

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

const NEW_PROJECT = "new-project"
const NO_PROJECT = "no-project"

/** Where this chat can go: another folder, out of the one it is in, or a new one. */
const moves = computed<MenuItem[]>(() => [
  ...props.projects
    .filter((project) => project.id !== props.chat.project_id)
    .map((project) => ({ name: project.id, label: project.name, icon: "folder" })),
  ...(props.chat.project_id
    ? [{ name: NO_PROJECT, label: "No project", icon: "folder_off" }]
    : []),
  { name: NEW_PROJECT, label: "New project…", icon: "create_new_folder" },
])

function pick(name: string) {
  if (name === NEW_PROJECT) emit("newProject")
  else emit("move", name === NO_PROJECT ? null : name)
}
</script>

<template>
  <div
    class="ai-chat-row"
    :class="{ 'ai-chat-row--active': active, 'ai-chat-row--pinned': chat.pinned }"
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
        icon="push_pin"
        :tooltip="chat.pinned ? 'Unpin chat' : 'Pin chat'"
        :active="chat.pinned"
        compact
        :data-testid="`ai-pin-${chat.id}`"
        @click="emit('pin', !chat.pinned)"
      />
      <span>
        <AppIconButton
          icon="folder"
          tooltip="Move to project"
          compact
          :data-testid="`ai-move-${chat.id}`"
        />
        <AppMenu
          :items="moves"
          @select="pick"
        />
      </span>
      <AppIconButton
        icon="archive"
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
/* Trap: display:none drops the buttons from the accessibility tree, so without
   :hover neither keyboard focus nor getByRole reaches them. The active row and
   a pinned one stay exposed — the pin is the answer to why it is up there. */
.ai-chat-row--active .ai-chat-row__actions,
.ai-chat-row--pinned .ai-chat-row__actions,
.ai-chat-row:hover .ai-chat-row__actions,
.ai-chat-row:focus-within .ai-chat-row__actions { display: flex; }
</style>
