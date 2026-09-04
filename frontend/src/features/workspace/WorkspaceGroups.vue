<script setup lang="ts">
import { computed, ref } from "vue"

import { AppButton, AppInput, AppMenu, AppTooltip, useConfirm, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"
import type { WorkspaceApi } from "@/shared/workspace"

import { groupNameProblem } from "./groups"
import type { TabGroup } from "./groups"
import type { Panel } from "./panels"
import { useTabGroups } from "./useTabGroups"

const props = defineProps<{ userId: string; workspace: WorkspaceApi<Panel> }>()
const toast = useToast()
const library = useTabGroups(props.userId, props.workspace, useConfirm(), toast)
const { groups, busy } = library
const editing = ref<{ id?: string } | null>(null)
const name = ref("")
const problem = computed(() => groupNameProblem(name.value, groups.value, editing.value?.id))
const menuItems = [
  { name: "update-group", label: "Update from current layout", icon: "save" },
  { name: "rename-group", label: "Rename", icon: "edit" },
  { name: "delete-group", label: "Delete", icon: "delete", danger: true },
]

function askForName(group?: TabGroup) {
  name.value = group?.name ?? ""
  editing.value = group === undefined ? {} : { id: group.id }
}

function saveName() {
  const edit = editing.value
  if (edit === null || problem.value) return
  const saved = edit.id === undefined ? library.save(name.value) : library.rename(edit.id, name.value)
  if (saved) editing.value = null
}

function select(action: string, group: TabGroup) {
  if (busy.value) return
  if (action === "rename-group") askForName(group)
  if (action === "delete-group") void library.remove(group)
  if (action === "update-group" && library.update(group.id)) toast.success(`Updated "${group.name}".`)
}
</script>

<template>
  <div
    class="workspace-groups"
    aria-label="Saved tab groups"
    data-testid="workspace-groups"
  >
    <div class="workspace-groups__list">
      <div
        v-for="group in groups"
        :key="group.id"
        class="workspace-groups__group"
        :data-testid="`tab-group-${group.id}`"
      >
        <AppButton
          variant="quiet"
          size="sm"
          icon="view_column"
          :aria-label="`Open group ${group.name}`"
          :disable="busy || editing !== null"
          data-testid="open-tab-group"
          @click="library.open(group)"
        >
          <span class="workspace-groups__name">{{ group.name }}</span>
          <AppTooltip>{{ group.name }}</AppTooltip>
        </AppButton>
        <AppButton
          variant="quiet"
          size="sm"
          icon="more_vert"
          :aria-label="`Manage group ${group.name}`"
          :disable="busy || editing !== null"
          data-testid="manage-tab-group"
        >
          <AppTooltip>Manage group</AppTooltip>
          <AppMenu
            :items="menuItems"
            @select="select($event, group)"
          />
        </AppButton>
      </div>
    </div>
    <AppButton
      variant="quiet"
      size="sm"
      icon="bookmark_add"
      label="Save group"
      class="workspace-groups__save"
      :disable="busy || editing !== null"
      data-testid="save-tab-group"
      @click="askForName()"
    />
    <WindowDialog
      :model-value="editing !== null"
      :title="editing?.id === undefined ? 'Save tab group' : 'Rename tab group'"
      size="sm"
      data-testid="tab-group-name-dialog"
      @update:model-value="editing = null"
    >
      <div class="workspace-groups__form">
        <AppInput
          v-model="name"
          label="Group name"
          :error="name.length > 0 ? problem : ''"
          autofocus
          maxlength="80"
          data-testid="tab-group-name"
          @keydown.enter.prevent="saveName"
        />
      </div>
      <template #actions>
        <AppButton
          variant="quiet"
          label="Cancel"
          @click="editing = null"
        />
        <AppButton
          label="Save"
          :disable="Boolean(problem) || busy"
          data-testid="confirm-tab-group-name"
          @click="saveName"
        />
      </template>
    </WindowDialog>
  </div>
</template>

<style scoped>
.workspace-groups {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: var(--dp-space-2);
  margin-inline: var(--dp-space-3);
}
.workspace-groups__list {
  display: flex;
  min-width: 0;
  gap: var(--dp-space-2);
  overflow-x: auto;
  scrollbar-width: thin;
}
.workspace-groups__group {
  display: flex;
  flex: none;
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
}
.workspace-groups__save {
  flex: none;
}
.workspace-groups__name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.workspace-groups__form {
  padding: var(--dp-space-3);
}
</style>
