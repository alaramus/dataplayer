<script setup lang="ts">
import { computed, inject, ref } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { COLLAPSED_PX, MIN_PANEL_PX } from "./model"
import type { LayoutNode } from "./model"
import { sharesOf } from "./shares"
import type { Share } from "./shares"
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
    const slot = { child, index, share: shares[index] ?? { share: 0, gaps: 0 }, after: previous }
    previous = index
    return [slot]
  })
})

/**
 * A collapsed child takes a fixed strip and the rest divide what is left in
 * proportion to their shares. That is why neither collapsing nor hiding ever
 * touches `sizes`: the size a section had is still written where it belongs.
 *
 * The room of a section that is not drawn is a share of the row, but the gap
 * in front of it and its own two edges are pixels the row simply stops
 * spending. They go back as the basis of the first section that takes that
 * room, so that what is left to divide is the same whether a column is on the
 * screen or on the bar, and the columns in front of it do not move by a pixel
 * when it comes back. A card counts its own edges in the basis as well, which is what
 * they cost already: a basis below them is raised to them.
 *
 * Written as three properties and not as `flex`, because a shorthand holding a
 * `calc` is thrown away whole where it is not understood.
 */
function styleFor(child: LayoutNode, share: Share) {
  if (child.kind === "leaf" && child.collapsed) {
    return { flexGrow: "0", flexShrink: "0", flexBasis: `${String(COLLAPSED_PX)}px` }
  }
  const cards = String((child.kind === "leaf" ? 1 : 0) + share.gaps)
  const gaps = String(share.gaps)
  return {
    flexGrow: String(share.share),
    flexShrink: "1",
    flexBasis: `calc(var(--dp-workspace-card-edges) * ${cards} + var(--dp-workspace-inset) * ${gaps})`,
  }
}

/**
 * How much of a section answers to the border beside it: what it is on the
 * screen, less the basis it holds whatever the row does — its own edges and
 * the gaps of the sections that are not drawn.
 */
function stretchOf(index: number): number {
  const found = element.value?.querySelector(`:scope > [data-section="${String(index)}"]`)
  if (!(found instanceof HTMLElement)) return 0
  const box = found.getBoundingClientRect()
  const length =
    props.node.kind === "split" && props.node.direction === "row" ? box.width : box.height
  // Computed rather than read back from the style: a `calc` of two variables
  // arrives here as the pixels it came to.
  const basis = Number.parseFloat(getComputedStyle(found).flexBasis)
  return length - (Number.isFinite(basis) ? basis : 0)
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
 * section where it is. Their shares and not their sizes: a share is what the
 * row divides its pixels by, and a size leaves out the room a hidden column
 * lent — with the catalog column empty, a pixel was read as half of one and
 * every minimum came out half as wide.
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
  let shares = 0
  let pixels = 0
  for (const index of indexes) {
    const child = props.node.children[index]
    if (child === undefined) return 0
    if (child.kind === "leaf" && child.collapsed) return 0
    shares += slots.value.find((slot) => slot.index === index)?.share.share ?? 0
    pixels += stretchOf(index)
  }
  return pixels > 0 ? shares / pixels : 0
}

/**
 * The narrowest this child may be dragged to. Only a section across a row has
 * a minimum of its own; a height, and a split of sections, keep MIN_PANEL_PX.
 */
function minPxOf(index: number): number {
  if (props.node.kind !== "split" || props.node.direction !== "row") return MIN_PANEL_PX
  const child = props.node.children[index]
  if (child?.kind !== "leaf") return MIN_PANEL_PX
  return workspace.sectionMinWidthOf(child.accepts ?? null)
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
    minPxOf(beforeIndex) * percent,
    minPxOf(afterIndex) * percent
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
