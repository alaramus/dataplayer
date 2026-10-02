<script setup lang="ts">
import { computed } from "vue"

import type { ConnectorPublic } from "@/client"
import ConnectorIcon from "@/features/connectors/ConnectorIcon.vue"
import { AppEmptyState, AppSpinner } from "@/shared/ui"
import { panelColorStyle } from "@/shared/ui/panelColor"

/**
 * The sources of the workspace, one per row.
 *
 * Two things in a row and nothing else: the icon of the source type, carrying
 * what the last check said, and the name beside it. Everything that can be done to a
 * connection lives inside the window its icon opens — a menu here would be a
 * second home for the same commands, and two homes drift. See the spec, S1.
 */
const props = defineProps<{
  rows: ConnectorPublic[]
  loading: boolean
  emptyText?: string
  /** The connection whose catalog is being looked at, if any. */
  selectedId?: string | null
  /**
   * The connections that have a catalog open somewhere.
   *
   * A quieter version of the same mark rather than a fourth thing in the row:
   * a row is an icon, a name and a state dot, and there is nothing to add to
   * it. See P7.
   */
  openIds?: ReadonlySet<string>
  /**
   * What a row is carried as when it is dragged, or nothing when it is not:
   * the pipelines' list is dragged onto a canvas (D175), Data's is not.
   */
  dragType?: string
}>()

const emit = defineEmits<{
  open: [connector: ConnectorPublic]
  edit: [connector: ConnectorPublic]
}>()

const selected = computed(() => props.selectedId ?? null)
const open = computed(() => props.openIds ?? new Set<string>())

function startDrag(event: DragEvent, connector: ConnectorPublic) {
  if (props.dragType === undefined || event.dataTransfer === null) return
  event.dataTransfer.setData(props.dragType, connector.id)
  event.dataTransfer.setData("text/plain", connector.name)
  event.dataTransfer.effectAllowed = "copy"
}
</script>

<template>
  <AppSpinner v-if="loading" />

  <AppEmptyState
    v-else-if="rows.length === 0"
    :text="emptyText ?? 'No connections yet'"
  />

  <div
    v-else
    class="connector-list"
    data-testid="connector-list"
  >
    <!-- A div and not a button: the row carries the icon button that opens the
         window, and a button inside a button is markup no browser agrees
         about. -->
    <div
      v-for="connector in rows"
      :key="connector.id"
      role="button"
      tabindex="0"
      class="connector-list__row"
      :class="{
        'connector-list__row--open': open.has(connector.id),
        'connector-list__row--selected': connector.id === selected,
      }"
      :style="panelColorStyle(connector.tab_color)"
      :data-testid="`connector-${connector.name}`"
      :draggable="dragType === undefined ? undefined : 'true'"
      @dragstart="startDrag($event, connector)"
      @click="emit('open', connector)"
      @keydown.enter="emit('open', connector)"
      @keydown.space.prevent="emit('open', connector)"
    >
      <!-- The icon carries the state dot, exactly as it does in the strip a
           collapsed column leaves behind: what a press means differs, what is
           drawn does not. -->
      <span @click.stop>
        <ConnectorIcon
          :connector-id="connector.id"
          :name="connector.name"
          :adapter-type="connector.adapter_type"
          :enabled="connector.enabled"
          tooltip="Edit connection"
          :testid="`connector-edit-${connector.name}`"
          @click="emit('edit', connector)"
        />
      </span>

      <span class="connector-list__name">{{ connector.name }}</span>
    </div>
  </div>
</template>

<style scoped>
.connector-list {
  display: flex;
  flex-direction: column;
}
.connector-list__row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  width: 100%;
  /* A pushed-aside column centres the icon in its forty pixels less a hairline
     either side, which is three pixels in from the edge of the card: the row
     starts its icon there too, so collapsing moves no icon sideways. */
  padding: 0 var(--dp-space-2) 0 calc(var(--dp-space-1) - 1px);
  /* An ordinary row of a list one picks from (D185): the icon's height and
     no more. A pixel above and below it made every row two pixels taller than
     the same icon in the pushed-aside column. */
  min-height: var(--dp-row-height);
  box-sizing: border-box;
  cursor: pointer;
}
/* Over the fill rather than instead of it: a hover rule is a class and a
   pseudo-class, so it outweighs the class that marks a row however the two
   are ordered — and the pointer arriving used to take the connection's colour
   off the row it was arriving at. A shadow spread over the whole box is the
   wash laid on top of whatever the row is filled with. */
.connector-list__row:hover {
  box-shadow: inset 0 0 0 999px var(--dp-hover);
}
/* Open somewhere, and the one being read. The full mark is written after the
   quiet one so that it wins where both apply.

   In the connection's own colour where it has one, so a row and the tabs it
   opened are visibly one thing. The row being read takes the colour whole and
   the text that contrasts with it; a row merely open takes a wash of it. A
   connection with no colour is marked just the same, in the plain colour its
   tabs are filled with and in the quiet half of that — the mark is the same
   mark either way, and only the colour of it is a choice. */
.connector-list__row--open {
  background: var(--dp-panel-quiet, var(--dp-panel-plain-quiet));
}
.connector-list__row--selected {
  background: var(--dp-panel-background, var(--dp-panel-plain));
  color: var(--dp-panel-foreground, inherit);
  font-weight: 500;
}
.connector-list__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
