<script setup lang="ts">
import type { QTreeProps } from "quasar"

/**
 * The catalog tree.
 *
 * Quasar's tree stays underneath, but a screen asks the kit for it: that keeps
 * the lint rule able to forbid <q-tree> outside the kit, and leaves one place
 * to change if the tree is ever replaced.
 */

/** Quasar exports no node type of its own; read off the props, the same way AppTable reads its columns. */
export type TreeNodes = QTreeProps["nodes"]

defineProps<{
  nodes: TreeNodes
  nodeKey: string
  expanded: string[]
  selected: string | null
}>()

defineEmits<{
  "update:expanded": [value: string[]]
  "update:selected": [value: string | null]
  lazyLoad: [payload: unknown]
}>()
</script>

<template>
  <q-tree
    :nodes="nodes"
    :node-key="nodeKey"
    :expanded="expanded"
    :selected="selected"
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
