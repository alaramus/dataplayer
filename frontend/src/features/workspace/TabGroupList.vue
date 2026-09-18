<script setup lang="ts">
import { computed, ref } from "vue"

import { AppButton, AppMenu, AppPopup, AppTooltip, useToast } from "@/shared/ui"

import { groupNameProblem } from "./groups"
import type { TabGroup } from "./groups"
import TabGroupNameDialog from "./TabGroupNameDialog.vue"
import type { TabGroupLibrary } from "./useTabGroups"

/** The rail block listing the saved tab groups: open, update, rename, delete. */
const props = defineProps<{
  groups: TabGroupLibrary
  /** Where the rail stands: the list opens away from the screen edge. */
  side: "left" | "right"
}>()

const toast = useToast()
const list = computed(() => props.groups.groups.value)
const busy = computed(() => props.groups.busy.value)
const listOpen = ref(false)
const anchor = computed(() => (props.side === "left" ? "top right" : "top left"))
const self = computed(() => (props.side === "left" ? "top left" : "top right"))

const renaming = ref<string | null>(null)
const name = ref("")
const problem = computed(() => groupNameProblem(name.value, list.value, renaming.value ?? undefined))

const menuItems = [
  { name: "update-group", label: "Update from current layout", icon: "save" },
  { name: "rename-group", label: "Rename", icon: "edit" },
  { name: "delete-group", label: "Delete", icon: "delete", danger: true },
]

function select(action: string, group: TabGroup) {
  listOpen.value = false
  if (busy.value) return
  if (action === "rename-group") {
    name.value = group.name
    renaming.value = group.id
  }
  if (action === "delete-group") void props.groups.remove(group)
  if (action === "update-group" && props.groups.update(group.id)) toast.success(`Updated "${group.name}".`)
}

function openGroup(group: TabGroup) {
  listOpen.value = false
  void props.groups.open(group)
}

function rename() {
  if (renaming.value === null || problem.value) return
  if (props.groups.rename(renaming.value, name.value)) renaming.value = null
}
</script>

<template>
  <!-- No click handler: the popup opens on anchor clicks by itself (the same
       way the manage menus do), and a manual toggle on top of it opens and
       instantly closes the list. v-model stays for closing it from the code.
       The popup lives inside the button so neighbours do not toggle it. -->
  <AppButton
    variant="quiet"
    size="sm"
    icon="bookmarks"
    aria-label="Saved tab groups"
    aria-haspopup="menu"
    :aria-expanded="listOpen"
    :disable="busy"
    data-testid="open-tab-groups"
  >
    <AppTooltip>Saved tab groups</AppTooltip>
    <AppPopup
      v-model="listOpen"
      :anchor="anchor"
      :self="self"
    >
      <div
        class="group-list"
        role="menu"
        aria-label="Saved tab groups"
      >
        <div
          v-if="!list.length"
          class="group-list__empty"
        >
          No saved groups yet
        </div>
        <div
          v-for="group in list"
          :key="group.id"
          class="group-list__row"
        >
          <AppButton
            variant="quiet"
            size="sm"
            icon="view_column"
            :label="group.name"
            :aria-label="`Open group ${group.name}`"
            :disable="busy"
            class="group-list__open"
            data-testid="open-tab-group"
            @click="openGroup(group)"
          />
          <AppButton
            variant="quiet"
            size="sm"
            icon="more_vert"
            :aria-label="`Manage group ${group.name}`"
            :disable="busy"
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
    </AppPopup>
  </AppButton>
  <TabGroupNameDialog
    v-model:name="name"
    :model-value="renaming !== null"
    title="Rename tab group"
    :problem="problem"
    :busy="busy"
    @update:model-value="(shown) => { if (!shown) renaming = null }"
    @confirm="rename"
  />
</template>

<style scoped>
/* The saved groups dropping out of the list button: one row per group, the
   name opening it and horizontal dots managing it. */
.group-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 220px;
  max-width: 320px;
  padding: 4px;
}
.group-list__row {
  display: flex;
  align-items: center;
  gap: 2px;
}
.group-list__open {
  flex: 1;
  min-width: 0;
  justify-content: flex-start;
}
.group-list__open :deep(.q-btn__content) {
  min-width: 0;
}
.group-list__empty {
  padding: 8px 12px;
  color: var(--dp-text-muted);
  font-size: 12px;
  white-space: nowrap;
}
</style>
