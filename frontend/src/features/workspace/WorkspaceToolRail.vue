<script setup lang="ts">
import { computed, ref } from "vue"

import SpaceSwitch from "@/features/dashboards/SpaceSwitch.vue"
import ServicesCommand from "@/features/services/ServicesCommand.vue"
import { AppButton, AppInput, AppMenu, AppPopup, AppTooltip, useToast } from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import CommandBar from "./CommandBar.vue"
import { GROUPS_LIST, GROUPS_SAVE, useToolRails } from "./toolRails"
import type { ToolRailZone } from "./toolRails"
import { groupNameProblem, suggestedGroupName } from "./groups"
import type { TabGroup } from "./groups"
import type { TabGroupLibrary } from "./useTabGroups"

/**
 * One vertical PyCharm-like tool rail: a half of one side of the workspace.
 *
 * Icon-only blocks, slightly thinner than the header, draggable within the
 * rail and across to the other three via native HTML drag and drop. The
 * order lives in `toolRails` and survives reloads through localStorage.
 *
 * The saved tab groups are exploded: the save button and the list button are
 * blocks of their own rather than one combined chunk, so each drags on its
 * own.
 */
const props = defineProps<{
  zone: ToolRailZone
  /** The one library of saved groups every rail shares; see WorkspacePage. */
  groups: TabGroupLibrary
}>()

const rails = useToolRails()
const blocks = computed(() => rails.blocksOf(props.zone).value)
const overIndex = ref<number | null>(null)
const onLeft = computed(() => props.zone.startsWith("left"))
const ZONE_TITLES: Record<ToolRailZone, string> = {
  "left-top": "Top left tools",
  "left-bottom": "Bottom left tools",
  "right-top": "Top right tools",
  "right-bottom": "Bottom right tools",
}
const zoneTitle = computed(() => ZONE_TITLES[props.zone])

const MIME = "application/x-dataplayer-tool"

function onDragStart(event: DragEvent, id: string) {
  if (event.dataTransfer === null) return
  event.dataTransfer.setData(MIME, id)
  // Firefox refuses the drop unless a plain type travels along.
  event.dataTransfer.setData("text/plain", id)
  event.dataTransfer.effectAllowed = "move"
}

function takeId(event: DragEvent): string {
  return event.dataTransfer?.getData(MIME) || event.dataTransfer?.getData("text/plain") || ""
}

function onItemDrop(event: DragEvent, index: number) {
  event.preventDefault()
  event.stopPropagation()
  overIndex.value = null
  const id = takeId(event)
  if (id === "") return
  rails.placeBlock(id, props.zone, index)
}

function onRailDrop(event: DragEvent) {
  if ((event.target as HTMLElement | null)?.closest?.(".tool-rail__block") !== null) return
  event.preventDefault()
  overIndex.value = null
  const id = takeId(event)
  if (id === "") return
  rails.placeBlock(id, props.zone, blocks.value.length)
}

const toast = useToast()
const groupList = computed(() => props.groups.groups.value)
const busy = computed(() => props.groups.busy.value)
const hasGroups = computed(() => groupList.value.length > 0)

/** Framed as one group only when the block holds several buttons. */
function isGrouped(id: string): boolean {
  return id === "spaces"
}

/** The saved-groups list: open beside the button, away from the screen edge. */
const listOpen = ref(false)
const menuAnchor = computed(() => (onLeft.value ? "top right" : "top left"))
const menuSelf = computed(() => (onLeft.value ? "top left" : "top right"))

const editingId = ref<string | null>(null)
const saving = ref(false)
const name = ref("")
const problem = computed(() => groupNameProblem(name.value, groupList.value, editingId.value ?? undefined))

function askSave() {
  name.value = suggestedGroupName(groupList.value)
  editingId.value = null
  saving.value = true
}

function askRename(group: TabGroup) {
  name.value = group.name
  editingId.value = group.id
  saving.value = false
}

function saveName() {
  if (problem.value) return
  if (editingId.value !== null) {
    if (props.groups.rename(editingId.value, name.value)) {
      editingId.value = null
      saving.value = false
    }
    return
  }
  if (props.groups.save(name.value)) saving.value = false
}

function closeDialog() {
  editingId.value = null
  saving.value = false
}

const menuItems = [
  { name: "update-group", label: "Update from current layout", icon: "save" },
  { name: "rename-group", label: "Rename", icon: "edit" },
  { name: "delete-group", label: "Delete", icon: "delete", danger: true },
]

function select(action: string, group: TabGroup) {
  listOpen.value = false
  if (busy.value) return
  if (action === "rename-group") askRename(group)
  if (action === "delete-group") void props.groups.remove(group)
  if (action === "update-group" && props.groups.update(group.id)) toast.success(`Updated "${group.name}".`)
}

function openListed(group: TabGroup) {
  listOpen.value = false
  void props.groups.open(group)
}
</script>

<template>
  <div
    class="tool-rail"
    :class="{
      'tool-rail--empty': blocks.length === 0,
      'tool-rail--tail': overIndex === blocks.length,
    }"
    :data-testid="`tool-rail-${zone}`"
    :aria-label="zoneTitle"
    @dragover.prevent="overIndex = blocks.length"
    @dragleave="overIndex = null"
    @drop="onRailDrop"
  >
    <div
      v-for="(id, index) in blocks"
      :key="id"
      class="tool-rail__block"
      :class="{
        'tool-rail__block--over': overIndex === index,
        'tool-rail__block--grouped': isGrouped(id),
      }"
      :data-testid="`tool-block-${id}`"
      @dragend="overIndex = null"
      @dragover.prevent.stop="overIndex = index"
      @drop="onItemDrop($event, index)"
    >
      <!-- The block drags by holding its buttons, PyCharm-style — the browser
           only starts the drag past its own threshold, so plain clicks still
           fire on the buttons. -->
      <div
        class="tool-rail__content"
        draggable="true"
        @dragstart="onDragStart($event, id)"
      >
        <SpaceSwitch
          v-if="id === 'spaces'"
          icon-only
        />
        <CommandBar
          v-else-if="id === 'queries'"
          icon-only
        />
        <ServicesCommand
          v-else-if="id === 'services'"
          icon-only
        />
        <!-- Two separate blocks: the save button, and the saved-groups list
             button beside it. The list button always stands; with no groups
             yet its menu says so. -->
        <template v-else-if="id === GROUPS_SAVE">
          <AppButton
            variant="quiet"
            size="sm"
            icon="bookmark_add"
            aria-label="Save group"
            :disable="busy"
            data-testid="save-tab-group"
            @click="askSave"
          >
            <AppTooltip>Save group</AppTooltip>
          </AppButton>
          <WindowDialog
            :model-value="saving"
            title="Save tab group"
            size="sm"
            data-testid="tab-group-name-dialog"
            @update:model-value="closeDialog"
          >
            <div class="tool-rail__form">
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
                @click="closeDialog"
              />
              <AppButton
                label="Save"
                :disable="Boolean(problem) || busy"
                data-testid="confirm-tab-group-name"
                @click="saveName"
              />
            </template>
          </WindowDialog>
        </template>
        <template v-else-if="id === GROUPS_LIST">
          <!-- No click handler: the popup opens on anchor clicks by itself
               (the same way the manage menus do), and a manual toggle on
               top of it opens and instantly closes the list. v-model stays
               for closing it from the code. The popup lives inside the
               button so neighbours do not toggle it. -->
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
              :anchor="menuAnchor"
              :self="menuSelf"
            >
              <div
                class="group-list"
                role="menu"
                aria-label="Saved tab groups"
              >
                <div
                  v-if="!hasGroups"
                  class="group-list__empty"
                >
                  No saved groups yet
                </div>
                <div
                  v-for="group in groupList"
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
                    @click="openListed(group)"
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
        </template>
      </div>
    </div>
    <WindowDialog
      :model-value="editingId !== null"
      title="Rename tab group"
      size="sm"
      data-testid="tab-group-name-dialog"
      @update:model-value="closeDialog"
    >
      <div class="tool-rail__form">
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
          @click="closeDialog"
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
.tool-rail {
  /* No side panels — only the rails. Transparent halves sharing each side
     equally; the empty half below the buttons is the drop target for
     appending to the end, and an emptied rail stays a visible target. */
  flex: 1 1 0;
  min-height: 0;
  width: fit-content;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  /* No top padding: a 32 px button then stands level with the 32 px tab strip
     of the cards beside it instead of starting a block below them. */
  padding: 0 2px 4px;
  overflow: visible;
  background: transparent;
}
/* An emptied rail keeps the width of a filled one (32px buttons plus the
   edge padding), so it stays a drop target instead of collapsing. */
.tool-rail--empty {
  min-width: 36px;
}
/* A drop past the last button lands here: say so while the hand is over it. */
.tool-rail--tail .tool-rail__block:last-child {
  border-bottom: 2px solid var(--dp-action-secondary);
}
.tool-rail--empty.tool-rail--tail {
  box-shadow: inset 0 0 0 2px var(--dp-action-secondary);
  border-radius: 8px;
}
.tool-rail__block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 4px 0;
  border-top: 2px solid transparent;
  user-select: none;
}
/* The topmost block keeps no top padding either, for the same level stand —
   including the 2 px its drop-indicator border always reserves. */
.tool-rail__block:first-child {
  padding-top: 0;
  margin-top: -2px;
}
/* The grouping frame lives only on blocks of several buttons: a lone
   button is framed by the button itself. */
.tool-rail__block--grouped {
  border-radius: 8px;
}
.tool-rail__block--grouped:hover {
  background: var(--dp-panel-quiet, var(--dp-panel-plain-quiet));
}
.tool-rail__block--over {
  border-top-color: var(--dp-action-secondary);
}
.tool-rail__content {
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: grab;
}
.tool-rail__content:active {
  cursor: grabbing;
}
/* Roomier buttons than the footer bars they came from: a rail button is a
   bigger target than a bar button, and the cramped dense ones read as broken. */
.tool-rail__content :deep(.q-btn) {
  min-width: 32px;
  min-height: 32px;
}
.tool-rail__content :deep(.q-btn .q-icon) {
  font-size: 20px;
}
/* The reused bar components were laid out for a horizontal footer; here they
   stand in a vertical icon column. */
.tool-rail__content :deep(.space-switch) {
  flex-direction: column;
  padding-right: 0;
  border-right: none;
  gap: 2px;
}
.tool-rail__content :deep(.command-bar),
.tool-rail__content :deep(.services-command) {
  justify-content: center;
}
.tool-rail__form {
  padding: var(--dp-space-3);
}
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
