<script setup lang="ts">
import { inject, ref } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { COLLAPSED_PX, MIN_PANEL_PX } from "./model"
import type { LayoutNode } from "./model"
import WorkspaceLeaf from "./WorkspaceLeaf.vue"
import WorkspaceSeparator from "./WorkspaceSeparator.vue"

const props = defineProps<{ node: LayoutNode }>()

const injected = inject(workspaceKey)
if (injected === undefined) throw new Error("WorkspaceNode used outside a WorkspaceRoot")
// See WorkspaceLeaf.vue: narrowing a const past a throw guard does not reach
// a later function declaration, so the non-undefined type is restated once.
const workspace: WorkspaceContext = injected

const element = ref<HTMLElement | null>(null)

/**
 * A collapsed child takes a fixed strip and the rest divide what is left in
 * proportion to their stored sizes. That is why collapsing never touches
 * `sizes`: the size a section had is still written where it belongs.
 */
function styleFor(child: LayoutNode, index: number) {
  if (child.kind === "leaf" && child.collapsed) {
    return { flex: `0 0 ${String(COLLAPSED_PX)}px` }
  }
  const size = props.node.kind === "split" ? (props.node.sizes[index] ?? 0) : 100
  return { flex: `${String(size)} 1 0%` }
}

/**
 * The length of this split along its own direction, measured now.
 *
 * Deliberately not a computed: getBoundingClientRect is not reactive, so a
 * memoised value would keep answering with the size the container had when it
 * first mounted, and every drag after a window resize would convert pixels at
 * the wrong scale.
 */
function lengthPx(): number {
  if (element.value === null) return 0
  const box = element.value.getBoundingClientRect()
  return props.node.kind === "split" && props.node.direction === "row" ? box.width : box.height
}

function onMove(index: number, deltaPx: number) {
  if (props.node.kind !== "split") return
  const total = lengthPx()
  if (total <= 0) return
  workspace.resize(
    props.node.id,
    index,
    (deltaPx / total) * 100,
    (MIN_PANEL_PX / total) * 100
  )
}

/** Pressing rather than dragging a border brings back whichever side is collapsed. */
function onToggle(index: number) {
  if (props.node.kind !== "split") return
  for (const child of [props.node.children[index], props.node.children[index + 1]]) {
    if (child === undefined) continue
    if (child.kind === "leaf" && child.collapsed) {
      workspace.toggleCollapse(child.id)
      return
    }
  }
}
</script>

<template>
  <WorkspaceLeaf
    v-if="node.kind === 'leaf'"
    :leaf="node"
    :collapsible="false"
  />
  <div
    v-else
    ref="element"
    class="workspace-node"
    :style="{ flexDirection: node.direction }"
  >
    <template
      v-for="(child, index) in node.children"
      :key="child.id"
    >
      <WorkspaceSeparator
        v-if="index > 0"
        :direction="node.direction"
        @move="onMove(index - 1, $event)"
        @toggle="onToggle(index - 1)"
      />
      <WorkspaceLeaf
        v-if="child.kind === 'leaf'"
        :leaf="child"
        :collapsible="true"
        :style="styleFor(child, index)"
      />
      <WorkspaceNode
        v-else
        :node="child"
        :style="styleFor(child, index)"
      />
    </template>
  </div>
</template>

<style scoped>
.workspace-node {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
}
</style>
