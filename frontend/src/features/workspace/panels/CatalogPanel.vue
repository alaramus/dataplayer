<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import CatalogActions from "@/features/catalog/CatalogActions.vue"
import CatalogList from "@/features/catalog/CatalogList.vue"
import { useCatalogLevel } from "@/features/catalog/useCatalogLevel"
import { showsPath } from "@/features/catalog/nodes"
import type { ListNode } from "@/features/catalog/nodes"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppBanner, AppIconButton, AppInput, AppSelect, useToast } from "@/shared/ui"

const props = defineProps<{
  panelId: string
  connectorId: string
  title: string
  adapterType: string
}>()

const toast = useToast()
const workspace = useWorkspaceActions()
const connectorId = computed(() => props.connectorId)
const rootLabel = computed(() => props.title)
const level = useCatalogLevel(connectorId, rootLabel)

/**
 * Whether the first level has come back.
 *
 * What the head shows follows from what the level holds, and before the first
 * answer it holds nothing — which reads the same as a level with nothing to
 * filter by. Deciding then would draw the path for one round trip and take it
 * away again on every source that does have groupings. `loading` cannot stand
 * in for this: it goes up on every later reload too, and the head would blink
 * each time.
 */
const answered = ref(false)

// The level that is on screen, not the root: the path and the ticks are where
// the user put them, and going back to the top is navigation rather than a
// refresh.
useReloadable(props.panelId, async () => {
  await level.reload(level.path.value[level.path.value.length - 1]?.id ?? null)
})

onMounted(() => {
  void level.load().finally(() => {
    answered.value = true
  })
})

const groupOptions = computed(() =>
  level.groups.value.map((group) => ({ label: group.label, value: group.id }))
)

const showPath = computed(
  () => answered.value && showsPath(level.path.value.length, level.groups.value)
)

/** What the level is called, for a form that acts on the level itself. */
const levelLabel = computed(
  () => level.path.value[level.path.value.length - 1]?.label ?? props.title
)

/** What is ticked, in one phrase, for a form that acts on the ticked nodes. */
const checkedLabel = computed(() => {
  const ticked = level.checkedNodes.value
  if (ticked.length === 1) return ticked[0]?.label ?? ""
  return `${String(ticked.length)} items`
})

/** A click opens what can be read and walks into what cannot. */
function onOpen(node: ListNode) {
  if (node.role === "container") {
    void level.enter(node)
    return
  }
  if (node.readable) {
    workspace.openRows({
      connectorId: props.connectorId,
      nodeId: node.id,
      title: node.label,
      connectorName: props.title,
      adapterType: props.adapterType,
    })
    return
  }
  // Said rather than left silent: a picture opens no tab, and without a word
  // the click looks like it did nothing at all.
  toast.info(`${node.label} cannot be read as rows`)
}

function onToggle(id: string, on: boolean) {
  level.checked.value = on
    ? [...level.checked.value, id]
    : level.checked.value.filter((other) => other !== id)
}

async function afterAction(reloadNodeIds: (string | null)[]) {
  for (const nodeId of reloadNodeIds) await level.reload(nodeId)
}
</script>

<template>
  <div class="catalog-panel">
    <div class="catalog-panel__head">
      <div class="catalog-panel__bar">
        <!-- Where we are, on the same line as the menu, not a stack of
             lines. Starting at a home button rather than at the name of the
             connection — the name is on the tab above, and what the first step
             of a path means is "back to the top". Whether it is drawn at all
             follows from what the level holds and never from the type of the
             source: see `showsPath` in `nodes.ts`. -->
        <div
          v-if="showPath"
          class="catalog-panel__crumbs"
          data-testid="catalog-path"
        >
          <AppIconButton
            icon="home"
            tooltip="The top of this connection"
            :disable="level.path.value.length < 2"
            data-testid="catalog-home"
            @click="level.goTo(0)"
          />
          <!-- The trail scrolls and the home button does not: a path deep
               enough to run out of the column must not carry away the one
               step that always gets back. -->
          <div class="catalog-panel__trail">
            <template
              v-for="(crumb, index) in level.path.value.slice(1)"
              :key="index"
            >
              <q-icon
                name="chevron_right"
                size="14px"
                class="catalog-panel__chevron"
              />
              <span
                class="catalog-panel__crumb"
                :class="{ 'catalog-panel__crumb--last': index === level.path.value.length - 2 }"
                role="button"
                tabindex="0"
                @click="level.goTo(index + 1)"
                @keydown.enter="level.goTo(index + 1)"
              >{{ crumb.label }}</span>
            </template>
          </div>
        </div>

        <!-- Beside the path and not under it. The line answers one question —
             where we are inside this source — and the answer takes the shape
             the level's own nodes give it: a path for a directory, a set of
             groupings for a database. Which of the two shows follows from the
             nodes, never from the type of the source. -->
        <!-- Named only while nothing is picked. A chosen schema is a chip
             saying its own name, and the word above it is both a repetition
             and a second line in a bar that has one — Quasar floats a label
             out of the field exactly when the field is filled. -->
        <AppSelect
          v-if="groupOptions.length"
          class="catalog-panel__groups"
          :model-value="level.selectedGroups.value"
          :options="groupOptions"
          :label="level.selectedGroups.value.length ? undefined : 'Schemas'"
          aria-label="Schemas"
          multiple
          compact
          data-testid="catalog-groups"
          @update:model-value="level.setGroups($event as string[])"
        />

        <CatalogActions
          class="catalog-panel__menu"
          :connector-id="connectorId"
          :level-id="level.currentId.value"
          :checked-ids="level.checked.value"
          :level-label="levelLabel"
          :checked-label="checkedLabel"
          @done="afterAction"
        />
      </div>

      <!-- On a line of its own: a filter is something a user types into, and
           typing needs the width. -->
      <AppInput
        v-model="level.filter.value"
        placeholder="Filter"
        compact
        data-testid="catalog-filter"
      />
    </div>

    <AppBanner
      v-if="level.error.value"
      tone="error"
      data-testid="catalog-error"
    >
      {{ level.error.value }}
    </AppBanner>

    <CatalogList
      class="catalog-panel__body"
      :items="level.items.value"
      :checked="level.checked.value"
      :loading="level.loading.value"
      :show-group="level.selectedGroups.value.length > 1"
      :has-parent="level.path.value.length > 1"
      @open="onOpen"
      @up="level.up"
      @toggle="onToggle"
      @toggle-all="level.toggleAll"
    />
  </div>
</template>

<style scoped>
/* The panel is a box of the height the section gave it: the head stays and
   only the list moves. See the spec, S10. */
.catalog-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.catalog-panel__head {
  flex: none;
  padding: 4px 4px 0;
}
/* One line of one height, whatever the source puts in it.
   A button and the menu are 32px, a field is 40, and a source with no
   groupings puts neither — so the height is stated here rather than left to
   be whatever the tallest thing in it happens to be. Moving between two
   connections must not move the list under them, and a rule about the panel
   is the only kind that a source type added later cannot break: what it
   brings centres in this line instead of setting it. */
.catalog-panel__bar {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 40px;
}
.catalog-panel__crumbs {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
  padding-right: 6px;
  border-radius: 999px;
  background: var(--dp-hover);
  font-size: 12px;
}
/* Takes what the line has left, and gives it back rather than pushing the
   menu off the end: the choice of schemas is a list of names, and a long one
   must not cost the column its only menu. */
.catalog-panel__groups {
  flex: 1;
  min-width: 0;
}
/* The menu keeps to the end of the line whether or not there is a path to
   push it there. */
.catalog-panel__menu {
  margin-left: auto;
}
.catalog-panel__trail {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  overflow-x: auto;
  white-space: nowrap;
  /* No bar: it would be thicker than the line it sits in. The path is
     scrolled by wheel or touch, and every step of it is also a click. */
  scrollbar-width: none;
}
.catalog-panel__trail::-webkit-scrollbar {
  display: none;
}
.catalog-panel__crumb,
.catalog-panel__chevron {
  flex: none;
}
.catalog-panel__crumb {
  cursor: pointer;
  padding: 2px 2px;
  color: var(--dp-link);
}
.catalog-panel__crumb--last {
  cursor: default;
  font-weight: 500;
  color: var(--dp-text-strong);
}
.catalog-panel__chevron {
  color: var(--dp-text-faint);
}
.catalog-panel__body {
  flex: 1;
  min-height: 0;
}
</style>
