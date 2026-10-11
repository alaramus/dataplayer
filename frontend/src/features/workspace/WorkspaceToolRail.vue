<script setup lang="ts">
import { computed, ref } from "vue"

import { useCurrentUser } from "@/shared/auth/currentUser"
import { t } from "@/shared/i18n"
import type { MessageKey } from "@/shared/i18n"

import { TOOL_BLOCKS } from "./toolBlocks"
import type { RailContext, ToolBlock } from "./toolBlocks"
import type { ToolRailZone } from "./toolRails"
import type { TabGroupLibrary } from "./useTabGroups"
import { useToolRails } from "./useToolRails"

/**
 * One vertical tool rail: a half of one side of the workspace (workspace.md,
 * Tool rails).
 *
 * Draws whichever blocks of `TOOL_BLOCKS` stand on it, icon-only, and moves
 * them within it and across to the other three by native drag and drop. What
 * a block is and what it needs is the registry's; a rail knows its zone and
 * the few things every block may ask of it.
 */
const props = defineProps<{
  zone: ToolRailZone
  /** The one library of saved groups every rail shares; see WorkspacePage. */
  groups: TabGroupLibrary
}>()

const rails = useToolRails()
const registry = new Map(TOOL_BLOCKS.map((block) => [block.id, block]))
const me = useCurrentUser()
const blocks = computed<ToolBlock[]>(() =>
  rails.arrangement.value[props.zone].flatMap((id) => {
    const block = registry.get(id)
    if (block === undefined) return []
    return block.superuserOnly === true && me.data.value?.is_superuser !== true ? [] : [block]
  })
)
const context = computed<RailContext>(() => ({
  groups: props.groups,
  side: props.zone.startsWith("left") ? "left" : "right",
}))
const overIndex = ref<number | null>(null)
const ZONE_TITLES: Record<ToolRailZone, MessageKey> = {
  "left-top": "workspace.rail.left_top",
  "left-bottom": "workspace.rail.left_bottom",
  "right-top": "workspace.rail.right_top",
  "right-bottom": "workspace.rail.right_bottom",
}

const MIME = "application/x-dataplayer-tool"

function onDragStart(event: DragEvent, id: string) {
  if (event.dataTransfer === null) return
  event.dataTransfer.setData(MIME, id)
  // Firefox refuses the drop unless a plain type travels along.
  event.dataTransfer.setData("text/plain", id)
  event.dataTransfer.effectAllowed = "move"
}

function takeId(event: DragEvent): string {
  const id = event.dataTransfer?.getData(MIME) || event.dataTransfer?.getData("text/plain") || ""
  return registry.has(id) ? id : ""
}

function onBlockDrop(event: DragEvent, before: string) {
  event.preventDefault()
  event.stopPropagation()
  overIndex.value = null
  const id = takeId(event)
  if (id !== "") rails.place(id, props.zone, before)
}

function onRailDrop(event: DragEvent) {
  if ((event.target as HTMLElement | null)?.closest?.(".tool-rail__block") !== null) return
  event.preventDefault()
  overIndex.value = null
  const id = takeId(event)
  if (id !== "") rails.place(id, props.zone, null)
}
</script>

<template>
  <div
    class="tool-rail"
    :class="{
      'tool-rail--empty': blocks.length === 0,
      'tool-rail--tail': overIndex === blocks.length,
      'tool-rail--bottom': zone.endsWith('bottom'),
    }"
    :data-testid="`tool-rail-${zone}`"
    :aria-label="t(ZONE_TITLES[zone])"
    @dragover.prevent="overIndex = blocks.length"
    @dragleave="overIndex = null"
    @drop="onRailDrop"
  >
    <div
      v-for="(block, index) in blocks"
      :key="block.id"
      class="tool-rail__block"
      :class="{
        'tool-rail__block--over': overIndex === index,
        'tool-rail__block--framed': block.framed,
      }"
      :data-testid="`tool-block-${block.id}`"
      @dragend="overIndex = null"
      @dragover.prevent.stop="overIndex = index"
      @drop="onBlockDrop($event, block.id)"
    >
      <!-- The block drags by holding its buttons — the browser only starts
           the drag past its own threshold, so plain clicks still fire on the
           buttons. -->
      <div
        class="tool-rail__content"
        draggable="true"
        @dragstart="onDragStart($event, block.id)"
      >
        <component
          :is="block.component"
          v-bind="block.props(context)"
        />
      </div>
    </div>
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
  gap: var(--dp-space-half);
  /* No top padding: a 32 px button then stands level with the 32 px tab strip
     of the cards beside it instead of starting a block below them. */
  padding: 0 var(--dp-space-half) var(--dp-space-1);
  overflow: visible;
  background: transparent;
}
/* The lower half keeps its buttons at its foot, by the bar at the bottom of
   the screen: started at the top of the half, they hung in the middle of the
   rail, tied to nothing. The empty room above them is still its drop target. */
.tool-rail--bottom {
  justify-content: flex-end;
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
  border-radius: var(--dp-radius-panel);
}
.tool-rail__block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--dp-space-1);
  padding: var(--dp-space-1) 0;
  border-top: 2px solid transparent;
  user-select: none;
}
/* The topmost block keeps no top padding either, for the same level stand —
   including the 2 px its drop-indicator border always reserves. */
.tool-rail__block:first-child {
  padding-top: 0;
  margin-top: calc(-1 * var(--dp-space-half));
}
/* The grouping frame lives only on blocks of several buttons: a lone
   button is framed by the button itself. It draws no hover fill: hovering
   the group used to wash it grey, which read as a selection. */
.tool-rail__block--framed {
  border-radius: var(--dp-radius-panel);
}
.tool-rail__block--over {
  border-top-color: var(--dp-action-secondary);
}
.tool-rail__content {
  display: flex;
  flex-direction: column;
  align-items: center;
}
/* Roomier buttons than the footer bars they came from: a rail button is a
   bigger target than a bar button, and the cramped dense ones read as broken. */
.tool-rail__content :deep(.q-btn) {
  min-width: 32px;
  min-height: 32px;
}
.tool-rail__content :deep(.q-btn .q-icon) {
  font-size: var(--dp-icon-md);
}
/* The reused bar components were laid out for a horizontal footer; here they
   stand in a vertical icon column. */
.tool-rail__content :deep(.space-switch) {
  flex-direction: column;
  padding-right: 0;
  border-right: none;
  gap: var(--dp-space-half);
}
.tool-rail__content :deep(.queries-command),
.tool-rail__content :deep(.services-command) {
  justify-content: center;
}
</style>
