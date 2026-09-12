<script setup lang="ts">
import { computed, inject, ref } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { COLLAPSED_PX, MIN_PANEL_PX } from "./model"
import type { LayoutNode } from "./model"
import { sharesOf } from "./shares"
import { isSectionHidden } from "./visibility"
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
 * A column that holds nothing and has nothing to say in that state.
 *
 * The engine does not decide what that means: it asks the feature what stands
 * in an empty section, and null is the answer that means "there is no such
 * column until something is opened in it". The whole tree is passed because a
 * pinned column keeps a role on screen rather than itself — see
 * `visibility.ts` and P4.
 */
function isHidden(child: LayoutNode): boolean {
  return isSectionHidden(
    workspace.tree.value,
    child,
    (accepts) => workspace.emptyOf(accepts) !== null
  )
}

/**
 * What is drawn, in order: the children that are on screen, the share each
 * takes now, and which of them carries a border in front of it.
 *
 * `index` is kept because it addresses the child in the tree, which a hidden
 * neighbour would otherwise shift.
 */
const slots = computed(() => {
  if (props.node.kind !== "split") return []
  const children = props.node.children
  const shares = sharesOf(
    props.node.sizes,
    children.map((child) => isHidden(child))
  )
  let previous: number | null = null
  return children.flatMap((child, index) => {
    if (isHidden(child)) return []
    const slot = { child, index, share: shares[index] ?? 0, after: previous }
    previous = index
    return [slot]
  })
})

/**
 * A collapsed child takes a fixed strip and the rest divide what is left in
 * proportion to their shares. That is why neither collapsing nor hiding ever
 * touches `sizes`: the size a section had is still written where it belongs.
 */
function styleFor(child: LayoutNode, share: number) {
  if (child.kind === "leaf" && child.collapsed) {
    return { flex: `0 0 ${String(COLLAPSED_PX)}px` }
  }
  return { flex: `${String(share)} 1 0%` }
}

function lengthOf(index: number): number {
  const found = element.value?.querySelector(`:scope > [data-section="${String(index)}"]`)
  if (!(found instanceof HTMLElement)) return 0
  const box = found.getBoundingClientRect()
  return props.node.kind === "split" && props.node.direction === "row" ? box.width : box.height
}

/**
 * How much of this split one pixel of the screen is worth right now, read off
 * the two sections the border is between.
 *
 * Measured rather than computed from the whole split: sections that are off
 * the screen leave their room to the ones that stay, so the sizes of the
 * sections showing no longer add up to a hundred, and a percentage taken
 * against the whole would move the border at the wrong speed. These two are
 * enough, because resizing trades room between them and leaves every other
 * section where it is.
 *
 * Deliberately not a computed: getBoundingClientRect is not reactive, so a
 * memoised value would keep answering with the size the sections had when
 * they first mounted, and every drag after a window resize would convert
 * pixels at the wrong scale.
 *
 * Nothing at all when either side is collapsed: a collapsed section keeps its
 * strip whatever its size says, so there is no room to trade across that
 * border, and dragging it used to move a border further along the row instead.
 * Pressing it still brings the section back.
 */
function percentPerPx(indexes: number[]): number {
  if (props.node.kind !== "split") return 0
  let sizes = 0
  let pixels = 0
  for (const index of indexes) {
    const child = props.node.children[index]
    if (child === undefined) return 0
    if (child.kind === "leaf" && child.collapsed) return 0
    sizes += props.node.sizes[index] ?? 0
    pixels += lengthOf(index)
  }
  return pixels > 0 ? sizes / pixels : 0
}

function onMove(beforeIndex: number, afterIndex: number, deltaPx: number) {
  if (props.node.kind !== "split") return
  const percent = percentPerPx([beforeIndex, afterIndex])
  if (percent <= 0) return
  workspace.resize(
    props.node.id,
    beforeIndex,
    afterIndex,
    deltaPx * percent,
    MIN_PANEL_PX * percent
  )
}

/** Pressing rather than dragging a border brings back whichever side is collapsed. */
function onToggle(beforeIndex: number, afterIndex: number) {
  if (props.node.kind !== "split") return
  for (const child of [props.node.children[beforeIndex], props.node.children[afterIndex]]) {
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
      v-for="slot in slots"
      :key="slot.child.id"
    >
      <WorkspaceSeparator
        v-if="slot.after !== null"
        :direction="node.direction"
        @move="onMove(slot.after, slot.index, $event)"
        @toggle="onToggle(slot.after, slot.index)"
      />
      <WorkspaceLeaf
        v-if="slot.child.kind === 'leaf'"
        :leaf="slot.child"
        :collapsible="true"
        :data-section="slot.index"
        :style="styleFor(slot.child, slot.share)"
      />
      <WorkspaceNode
        v-else
        :node="slot.child"
        :data-section="slot.index"
        :style="styleFor(slot.child, slot.share)"
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
