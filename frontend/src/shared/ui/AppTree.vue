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
}>()

defineEmits<{
  "update:expanded": [value: string[]]
  "update:selected": [value: string | null]
  lazyLoad: [payload: TreeLazyLoad]
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
