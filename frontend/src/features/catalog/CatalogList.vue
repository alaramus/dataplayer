<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"

import type { ListNode } from "@/features/catalog/nodes"
import { copyText } from "@/shared/clipboard"
import { AppCheckbox, AppEmptyState, AppIconButton, AppSpinner, useToast } from "@/shared/ui"

/**
 * One level of a catalog, as a list.
 *
 * The row says what it is and what it holds; the tick box says what an action
 * will be done to. Two gestures, because a directory has to be picked without
 * being walked into — see the spec, S5.
 */
const props = defineProps<{
  items: ListNode[]
  checked: string[]
  loading: boolean
  /**
   * Whether to name the grouping a row came from. It says nothing while only
   * one grouping is on, and in a column this narrow it costs the name of the
   * row it stands beside.
   */
  showGroup?: boolean
  /** What the current node is, so an empty level can say so. */
  emptyText?: string
  /**
   * Whether there is a level above this one.
   *
   * The way back is the first row of the list, as it is in every other
   * explorer, rather than a button in the head: it is a place among the
   * places, and the hand is already in the list. See the spec, S5.
   */
  hasParent?: boolean
  /**
   * Which row was arrived at, from the tab of a table that lives in it.
   *
   * Apart from `checked`, and marked differently: a tick means an action will
   * be done to the row, this means "here it is". Null, or an id this level
   * does not hold, marks nothing.
   */
  revealed?: string | null
}>()

const root = ref<HTMLElement | null>(null)
const toast = useToast()

/**
 * The name of a row, in the clipboard.
 *
 * The gesture lives on the icon rather than in a column of its own: a control
 * wanted only on the row under the pointer must not cost every row the width,
 * and the icon is already the one place on a row that says nothing a reader
 * needs while they are reaching for it.
 */
async function copyName(node: ListNode) {
  try {
    await copyText(node.label)
    toast.success(`Copied “${node.label}”`)
  } catch {
    toast.error("This browser would not let the name be copied")
  }
}

/**
 * Bring the pointed-at row into view.
 *
 * After the next render: the row may have arrived in the same change that
 * named it, when the level was read because the catalog had just been opened.
 * "nearest" and not "center" — a row already on screen must not make the list
 * jump.
 */
watch(
  () => props.revealed,
  async (id) => {
    if (id === null || id === undefined) return
    await nextTick()
    root.value?.querySelector('[data-revealed="true"]')?.scrollIntoView({ block: "nearest" })
  },
  { immediate: true }
)

const emit = defineEmits<{
  open: [node: ListNode]
  /**
   * One row, ticked or unticked. The new set is not computed here: `checked`
   * is a prop, and a prop only catches up on the next render — two ticks
   * inside one frame would both be computed from the same stale list and the
   * first would be lost.
   */
  toggle: [id: string, on: boolean]
  "toggle-all": [on: boolean]
  up: []
}>()

const allChecked = computed(
  () => props.items.length > 0 && props.items.every((node) => props.checked.includes(node.id))
)

const someChecked = computed(() => props.checked.length > 0 && !allChecked.value)

/**
 * What the level holds, and how much of it an action would be done to.
 *
 * The tally of ticks is of the whole level rather than of what the filter
 * leaves showing: a filter hides rows, it does not untick them, and the number
 * in brackets has to be the number the menu above would act on.
 */
const countLabel = computed(() => {
  const total = `${String(props.items.length)} ${props.items.length === 1 ? "item" : "items"}`
  if (props.checked.length === 0) return total
  return `${total} (${String(props.checked.length)} selected)`
})

</script>

<template>
  <div
    ref="root"
    class="catalog-list"
  >
    <div class="catalog-list__head">
      <AppCheckbox
        :model-value="allChecked"
        :indeterminate="someChecked"
        dense
        aria-label="Select everything here"
        data-testid="catalog-check-all"
        @update:model-value="emit('toggle-all', $event)"
      />
      <span
        class="catalog-list__count"
        data-testid="catalog-count"
      >{{ countLabel }}</span>
    </div>

    <AppSpinner v-if="loading" />

    <div
      v-else
      class="catalog-list__rows"
      data-testid="catalog-list"
    >
      <!-- Above everything, and above the empty state too: a folder with
           nothing in it is exactly where the way back matters most. -->
      <div
        v-if="hasParent"
        role="button"
        tabindex="0"
        class="catalog-list__row catalog-list__row--up"
        data-testid="catalog-up"
        @click="emit('up')"
        @keydown.enter="emit('up')"
        @keydown.space.prevent="emit('up')"
      >
        <!-- A tick box that is there and cannot be seen, rather than a spacer
             of a guessed width: this row has nothing to tick but has to line
             up with the rows that do, and only the control itself knows how
             wide it is. Hidden by visibility, so it is out of the tab order
             as well as out of sight. -->
        <span
          class="catalog-list__tick-space"
          aria-hidden="true"
        >
          <AppCheckbox
            :model-value="false"
            dense
          />
        </span>
        <q-icon
          name="drive_folder_upload"
          size="18px"
        />
        <span class="catalog-list__name">..</span>
      </div>

      <AppEmptyState
        v-if="items.length === 0"
        class="catalog-list__empty"
        :text="emptyText ?? 'Nothing here'"
      />

      <!-- A div and not a button: the row carries a tick box of its own, and a
           button inside a button is markup no browser agrees about. -->
      <div
        v-for="node in items"
        :key="node.id"
        role="button"
        tabindex="0"
        :aria-label="`Open ${node.label}`"
        class="catalog-list__row"
        :class="{
          'catalog-list__row--checked': checked.includes(node.id),
          'catalog-list__row--revealed': node.id === revealed,
          'catalog-list__row--sentence': node.kind === 'report',
        }"
        :data-testid="`catalog-node-${node.label}`"
        :data-revealed="node.id === revealed ? 'true' : undefined"
        @click="emit('open', node)"
        @keydown.enter="emit('open', node)"
        @keydown.space.prevent="emit('open', node)"
      >
        <span @click.stop>
          <AppCheckbox
            :model-value="checked.includes(node.id)"
            dense
            :aria-label="`Select ${node.label}`"
            :data-testid="`catalog-check-${node.label}`"
            @update:model-value="emit('toggle', node.id, $event)"
          />
        </span>

        <!-- The picture and the button that replaces it, one over the other
             and both 18px: swapping them must not move the name beside them. -->
        <span class="catalog-list__mark">
          <q-icon
            class="catalog-list__icon"
            :name="node.icon"
            size="18px"
          />
          <AppIconButton
            class="catalog-list__copy"
            icon="content_copy"
            :tooltip="`Copy “${node.label}”`"
            :data-testid="`catalog-copy-${node.label}`"
            @click.stop="copyName(node)"
            @keydown.enter.stop
            @keydown.space.stop
          />
        </span>
        <span class="catalog-list__name">{{ node.label }}</span>

        <span
          v-if="showGroup && node.group"
          class="catalog-list__group"
        >
          {{ node.group }}
        </span>
        <!-- Where a search found it, which only a search result carries. The
             name keeps the room it needs and this takes what is left (D76). -->
        <span
          v-if="node.location"
          class="catalog-list__location"
          :title="node.location"
        >
          {{ node.location }}
        </span>
        <!-- The hint is only on a caption that says nothing was counted: one
             word stands for a table nobody has analysed and for a view with
             no rows to count, and the column has room for neither reason. -->
        <span
          v-if="node.caption"
          class="catalog-list__caption"
          :title="node.captionHint"
          :data-testid="`catalog-caption-${node.label}`"
        >
          {{ node.caption }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.catalog-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}
.catalog-list__head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-2);
  padding: 0 var(--dp-space-2) var(--dp-space-half);
  border-bottom: 1px solid var(--dp-border-faint);
  flex: none;
}
.catalog-list__count {
  font-size: 11px;
  color: var(--dp-text-muted);
}
.catalog-list__location {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--dp-text-muted);
}
/* One level, one set of columns. The list is a grid so that what a row says
   stands under what the row above it says; a row is still a box of its own,
   carrying the hover and the tick, so it takes the columns with `subgrid`
   rather than dissolving into the list.

   Every column but the name may shrink to nothing: a long path found by a
   search must not leave the name 5ch wide. */
.catalog-list__rows {
  flex: 1;
  min-height: 0;
  overflow: auto;
  scrollbar-gutter: stable;
  /* Reserve space for classic scrollbars before rows arrive, and keep the
     shared columns clear of overlay scrollbars, which have no gutter. */
  padding-inline-end: var(--dp-space-3);
  display: grid;
  grid-template-columns:
    auto auto minmax(5ch, 1fr) minmax(0, auto) minmax(0, auto) minmax(0, auto);
  align-content: start;
  column-gap: var(--dp-space-2);
}
.catalog-list__empty {
  grid-column: 1 / -1;
  padding: var(--dp-space-1) var(--dp-space-2);
}
.catalog-list__row {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: subgrid;
  align-items: center;
  gap: var(--dp-space-2);
  padding: 1px var(--dp-space-2);
  cursor: pointer;
  /* Every row carries the outline, transparent, so that taking the mark off
     fades rather than blinks: a colour cannot be transitioned out of a rule
     that is no longer applied. An outline takes no space, so this costs
     nothing on the rows that never carry a mark. */
  outline: 2px solid transparent;
  outline-offset: -2px;
  transition: outline-color 400ms ease;
}
@media (prefers-reduced-motion: reduce) {
  .catalog-list__row {
    transition: none;
  }
}
.catalog-list__row:hover {
  background: var(--dp-hover);
}
/* Where the keyboard is. The row already carries an outline for the reveal
   mark, so focus colours that one - at once rather than fading in, because a
   place is not an announcement (U06). */
.catalog-list__row:focus-visible {
  outline-color: var(--dp-accent);
  border-radius: var(--dp-radius-control);
  transition: none;
}
.catalog-list__row--checked {
  background: var(--dp-selected);
}
/* An outline and not a fill: a fill is what a tick already means here, and
   "an action will be done to this" and "here it is" are not the same thing.
   It comes off after a few seconds — held longer it stops saying "here it is"
   and starts reading as a state the row is in.

   In the colour of the tab the press came from: the connection's own where it
   has one, and the plain fill every tab carries where it has not. The two ends
   of one gesture, drawn the same. */
.catalog-list__row--revealed {
  outline-color: var(--dp-panel-background, var(--dp-panel-plain));
  border-radius: var(--dp-radius-control);
}
.catalog-list__tick-space {
  visibility: hidden;
}
/* The icon of a row is also where its name is copied from. The button lies
   exactly over the picture, so the row under the pointer gains a gesture and
   loses no width, and nothing on the line moves when the pointer arrives. */
.catalog-list__mark {
  position: relative;
  flex: none;
  width: 18px;
  height: 18px;
}
.catalog-list__copy {
  position: absolute;
  inset: 0;
  min-width: 0;
  min-height: 0;
  padding: 0;
  opacity: 0;
  /* Out of reach rather than merely invisible, or a click meant for the row
     would land on a button nobody can see. Focus brings both back, so the
     gesture is there for a keyboard as well as for a pointer. */
  pointer-events: none;
}
.catalog-list__copy :deep(.q-icon) {
  font-size: 15px;
}
.catalog-list__row:hover .catalog-list__copy,
.catalog-list__copy:focus-within {
  opacity: 1;
  pointer-events: auto;
}
.catalog-list__row:hover .catalog-list__icon,
.catalog-list__mark:has(.catalog-list__copy:focus-within) .catalog-list__icon {
  opacity: 0;
}
/* The name comes first when there is not enough room: it is what the row is
   about, and the caption beside it is an aside. */
.catalog-list__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.catalog-list__group,
.catalog-list__caption {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  color: var(--dp-text-muted);
  white-space: nowrap;
}
/* Names of things, so their left edges line up; measurements, so their right
   edges do. */
.catalog-list__group {
  justify-self: start;
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-control);
  padding: 0 var(--dp-space-1);
}
.catalog-list__caption {
  justify-self: end;
}
/* A row whose caption is a sentence rather than a measurement.
   Only a report has one — it is the line the source wrote about what its
   statement answers — and a sentence in a column shared with "~8 rows" would
   set that column's width for every row in the list. So this one row lays
   itself out and takes the width it needs, leaving the columns to the rows
   that have something to line up. Its name still starts where the others do:
   the two things before it are a tick box and an 18px icon, on every row. */
.catalog-list__row--sentence {
  display: flex;
}
/* At the end of the row, where every other row's measurement is. Drawn right
   after the name it read as a second half of the name, which a line about
   what a report answers is not; the auto margin puts it where the counts are
   without giving it a column they would have to share. */
.catalog-list__row--sentence .catalog-list__caption {
  /* Shrinks far faster than the name beside it: the name is what the row is
     about, and a narrow panel should cut the aside rather than the subject. */
  flex: 0 100 auto;
  margin-inline-start: auto;
  padding-inline-start: var(--dp-space-3);
}
</style>
