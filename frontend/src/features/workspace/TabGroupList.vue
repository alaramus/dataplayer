<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import { AppButton, AppMenu, AppPopup, AppTooltip, useToast } from "@/shared/ui"
import { useSpaceStore } from "@/stores/space"

import { groupNameProblem, groupsUnavailableIn } from "./groups"
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
const space = useSpaceStore()
const unavailable = computed(() => groupsUnavailableIn(space.current))
const listOpen = ref(false)
const anchor = computed(() => (props.side === "left" ? "top right" : "top left"))
const self = computed(() => (props.side === "left" ? "top left" : "top right"))

const renaming = ref<string | null>(null)
const name = ref("")
const problem = computed(() => groupNameProblem(name.value, list.value, renaming.value ?? undefined))

const menuItems = computed(() => [
  { name: "update-group", label: "Update from current layout", icon: appIcons.save,
    disable: !props.groups.canSave.value, hint: "Open a tab first" },
  { name: "rename-group", label: "Rename", icon: appIcons.edit },
  { name: "delete-group", label: "Delete", icon: appIcons.delete, danger: true },
])

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
       The popup lives inside the button so neighbours do not toggle it; the
       tooltip hangs off a wrapper, as Save group's does, because a disabled
       Quasar button takes no pointer events. -->
  <span class="tab-group-list">
    <AppButton
      variant="quiet"
      size="sm"
      :icon="appIcons.bookmarks"
      aria-label="Saved tab groups"
      aria-haspopup="menu"
      :aria-expanded="listOpen"
      :disable="busy || unavailable !== null"
      data-testid="open-tab-groups"
    >
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
              :icon="appIcons.viewColumn"
              :label="group.name"
              :aria-label="`Open group ${group.name}`"
              :disable="busy || unavailable !== null"
              class="group-list__open"
              data-testid="open-tab-group"
              @click="openGroup(group)"
            />
            <AppButton
              variant="quiet"
              size="sm"
              :icon="appIcons.moreVert"
              :aria-label="`Manage group ${group.name}`"
              :disable="busy || unavailable !== null"
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
    <AppTooltip>{{ unavailable === null ? "Saved tab groups" : `Saved tab groups — ${unavailable}` }}</AppTooltip>
  </span>
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
.tab-group-list {
  display: inline-flex;
  align-items: center;
}
/* The saved groups dropping out of the list button: one row per group, the
   name opening it and horizontal dots managing it. */
.group-list {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-half);
  min-width: 220px;
  max-width: 320px;
  padding: var(--dp-space-1);
}
.group-list__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-half);
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
  padding: var(--dp-space-2) var(--dp-space-3);
  color: var(--dp-text-muted);
  font-size: 12px;
  white-space: nowrap;
}
</style>
