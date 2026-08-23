<script setup lang="ts">
import { onBeforeUnmount, onMounted, provide, ref } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import WorkspaceDragGhost from "./WorkspaceDragGhost.vue"
import WorkspaceNode from "./WorkspaceNode.vue"

const props = defineProps<{ context: WorkspaceContext }>()

provide(workspaceKey, props.context)

/** Where the hand is, so that what it carries can be drawn there. */
const pointer = ref<{ x: number; y: number } | null>(null)

/**
 * Every movement inside the workspace arrives here by bubbling, so this is the
 * one place that knows where the pointer is - and the one place a press turns
 * into a drag, which cannot be the section the tab came from: the pointer
 * leaves it immediately. See G1.
 */
function onPointerMove(event: PointerEvent) {
  pointer.value = { x: event.clientX, y: event.clientY }
  props.context.pointerMoved(event.clientX, event.clientY)
}

/**
 * A drag released anywhere at all is over.
 *
 * On the window rather than on the workspace: released outside every section,
 * the gesture comes to nothing, and without this the ghost would stay in the
 * hand with nothing holding it. A section that took the drop has already
 * ended it, so this arrives at a drag that is no longer there and does
 * nothing.
 */
function onWindowPointerUp() {
  props.context.endDrag(null, null)
}

onMounted(() => {
  window.addEventListener("pointerup", onWindowPointerUp)
})

onBeforeUnmount(() => {
  window.removeEventListener("pointerup", onWindowPointerUp)
})
</script>

<template>
  <div
    class="workspace"
    data-testid="workspace"
    @pointermove="onPointerMove"
  >
    <WorkspaceNode :node="context.tree.value" />

    <WorkspaceDragGhost
      v-if="context.dragging.value !== null && pointer !== null"
      :look="context.lookOf(context.dragging.value)"
      :x="pointer.x"
      :y="pointer.y"
    />
  </div>
</template>

<style scoped>
.workspace {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
</style>
