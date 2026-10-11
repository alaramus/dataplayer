<script setup lang="ts">
import type { QTree, QTreeProps } from "quasar"
import { computed, useTemplateRef } from "vue"

import { t } from "@/shared/i18n"

import AppCheckbox from "./AppCheckbox.vue"
import { leafKeys, tickStates, withTicks } from "./treeTicks"
import type { TickNode, TickState } from "./treeTicks"

/**
 * The catalog tree.
 *
 * Quasar's tree stays underneath, but a screen asks the kit for it: that keeps
 * the lint rule able to forbid <q-tree> outside the kit, and leaves one place
 * to change if the tree is ever replaced.
 */

/** Quasar exports no node type of its own; read off the props, the same way AppTable reads its columns. */
export type TreeNodes = QTreeProps["nodes"]

/**
 * The payload of a lazy load, read off the props for the same reason.
 *
 * Typed rather than `unknown`: a screen answers this with a real loader, and
 * an opaque payload would push a cast into every screen that has one.
 */
export type TreeLazyLoad = Parameters<NonNullable<QTreeProps["onLazyLoad"]>>[0]

const props = withDefaults(defineProps<{
  nodes: TreeNodes
  nodeKey: string
  expanded: string[]
  selected: string | null
  /**
   * Tick boxes, and which leaves are ticked. A tick on a branch ticks every
   * leaf under it; what comes back is always leaves, so a caller never has to
   * walk the tree to learn what a branch meant.
   *
   * The boxes are the kit's AppCheckbox rather than the tree's own, so Quasar
   * is told there is no ticking and the rule lives in treeTicks.ts.
   */
  ticked?: string[]
  tickable?: boolean
  /**
   * Whether clicking the selected row leaves it selected.
   *
   * Off by default, which is Quasar's own behaviour: a second click clears the
   * selection. A tree whose selection is the subject of a menu wants the
   * opposite — the menu would empty itself under the pointer.
   */
  keepSelection?: boolean
}>(), { ticked: () => [], tickable: false, keepSelection: false })

const emit = defineEmits<{
  "update:expanded": [value: string[]]
  "update:selected": [value: string | null]
  "update:ticked": [value: string[]]
  lazyLoad: [payload: TreeLazyLoad]
}>()

const tree = useTemplateRef<QTree>("tree")

const ticks = computed(() =>
  props.tickable ? tickStates(props.nodes, props.nodeKey, props.ticked) : new Map<string, TickState>()
)

function boxOf(node: TickNode): TickState | undefined {
  return ticks.value.get(String(node[props.nodeKey]))
}

function nameOf(node: TickNode): string {
  return typeof node.label === "string" ? node.label : String(node[props.nodeKey])
}

function tick(node: TickNode, on: boolean) {
  emit("update:ticked", withTicks(props.ticked, leafKeys(node, props.nodeKey), on))
}

/**
 * Open or close one branch, through the tree's own method.
 *
 * Not by pushing a key into `expanded`: a branch that loads its children when
 * it opens is opened by the tree, which is what asks for them. Setting the
 * array from outside marks it open and asks for nothing, so it stays shut.
 */
function setExpanded(key: string, open: boolean) {
  tree.value?.setExpanded(key, open)
}

function isExpanded(key: string): boolean {
  return tree.value?.isExpanded(key) === true
}

defineExpose({ setExpanded, isExpanded })
</script>

<template>
  <q-tree
    ref="tree"
    class="app-tree"
    :nodes="nodes"
    :node-key="nodeKey"
    :expanded="expanded"
    :selected="selected"
    :no-selection-unset="keepSelection"
    tick-strategy="none"
    @update:expanded="$emit('update:expanded', [...$event])"
    @update:selected="$emit('update:selected', $event)"
    @lazy-load="$emit('lazyLoad', $event)"
  >
    <template #default-header="scope">
      <!-- Pressing the box ticks without selecting the row: the checkbox
           keeps its click from the header, as the tree's own box did. -->
      <AppCheckbox
        v-if="boxOf(scope.node) !== undefined"
        class="app-tree__tick"
        :model-value="boxOf(scope.node) === true"
        :indeterminate="boxOf(scope.node) === null"
        dense
        :aria-label="t('kit.tree.tick', { name: nameOf(scope.node) })"
        @update:model-value="tick(scope.node, $event)"
      />
      <slot
        name="default-header"
        v-bind="scope"
      >
        {{ nameOf(scope.node) }}
      </slot>
    </template>
  </q-tree>
</template>

<style scoped>
.app-tree__tick {
  margin-right: var(--dp-space-1);
}
.app-tree :deep(.q-tree__node--selected) {
  background: var(--dp-selected);
  box-shadow: var(--dp-selected-edge);
  border-radius: var(--dp-radius-control);
}
.app-tree :deep(.q-tree__node--selected .q-tree__node-header-content) {
  color: var(--dp-text);
}
</style>
