<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"

import type { ListNode } from "@/features/catalog/nodes"
import { AppCheckbox, AppEmptyState, AppSpinner } from "@/shared/ui"

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
        :text="emptyText ?? 'Nothing here'"
      />

      <!-- A div and not a button: the row carries a tick box of its own, and a
           button inside a button is markup no browser agrees about. -->
      <div
        v-for="node in items"
        :key="node.id"
        role="button"
        tabindex="0"
        class="catalog-list__row"
        :class="{
          'catalog-list__row--checked': checked.includes(node.id),
          'catalog-list__row--revealed': node.id === revealed,
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
            :data-testid="`catalog-check-${node.label}`"
            @update:model-value="emit('toggle', node.id, $event)"
          />
        </span>

        <q-icon
          :name="node.icon"
          size="18px"
        />
        <span class="catalog-list__name">{{ node.label }}</span>

        <span
          v-if="showGroup && node.group"
          class="catalog-list__group"
        >
          {{ node.group }}
        </span>
        <span
          v-if="node.caption"
          class="catalog-list__caption"
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
  gap: 8px;
  padding: 0 8px 2px;
  border-bottom: 1px solid var(--dp-border-faint);
  flex: none;
}
.catalog-list__count {
  font-size: 11px;
  color: var(--dp-text-muted);
}
.catalog-list__rows {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.catalog-list__row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 1px 8px;
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
.catalog-list__row--checked {
  background: var(--dp-selected);
}
/* An outline and not a fill: a fill is what a tick already means here, and
   "an action will be done to this" and "here it is" are not the same thing.
   It comes off after a few seconds — held longer it stops saying "here it is"
   and starts reading as a state the row is in. */
.catalog-list__row--revealed {
  outline-color: var(--dp-focus-border);
  border-radius: 4px;
}
.catalog-list__tick-space {
  visibility: hidden;
}
/* The name comes first when there is not enough room: it is what the row is
   about, and the caption beside it is an aside. */
.catalog-list__name {
  flex: 1 1 auto;
  min-width: 5ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.catalog-list__group,
.catalog-list__caption {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  font-size: 11px;
  color: var(--dp-text-muted);
  white-space: nowrap;
}
.catalog-list__group {
  border: 1px solid var(--dp-border);
  border-radius: 3px;
  padding: 0 4px;
}
</style>
