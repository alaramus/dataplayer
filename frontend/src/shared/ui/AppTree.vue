<script setup lang="ts">
import type { QTree, QTreeProps } from "quasar"
import { useTemplateRef } from "vue"

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

defineProps<{
  nodes: TreeNodes
  nodeKey: string
  expanded: string[]
  selected: string | null
  /**
   * Whether clicking the selected row leaves it selected.
   *
   * Off by default, which is Quasar's own behaviour: a second click clears the
   * selection. A tree whose selection is the subject of a menu wants the
   * opposite — the menu would empty itself under the pointer.
   */
  keepSelection?: boolean
}>()

defineEmits<{
  "update:expanded": [value: string[]]
  "update:selected": [value: string | null]
  lazyLoad: [payload: TreeLazyLoad]
}>()

const tree = useTemplateRef<QTree>("tree")

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
    @update:expanded="$emit('update:expanded', [...$event])"
    @update:selected="$emit('update:selected', $event)"
    @lazy-load="$emit('lazyLoad', $event)"
  >
    <template #default-header="scope">
      <slot
        name="default-header"
        v-bind="scope"
      />
    </template>
  </q-tree>
</template>

<style scoped>
.app-tree :deep(.q-tree__node--selected) {
  background: var(--dp-selected);
  border-radius: var(--dp-radius-control);
}
.app-tree :deep(.q-tree__node--selected .q-tree__node-header-content) {
  color: var(--dp-text-strong);
}
</style>
