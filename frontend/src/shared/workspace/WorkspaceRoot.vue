<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue"

import type { WorkspaceContext } from "./context"
import WorkspaceFloatingWindows from "./WorkspaceFloatingWindows.vue"
import WorkspacePanels from "./WorkspacePanels.vue"
import WorkspaceDragGhost from "./WorkspaceDragGhost.vue"
import WorkspaceNode from "./WorkspaceNode.vue"

const props = defineProps<{ context: WorkspaceContext }>()

/** Where the hand is, so that what it carries can be drawn there. */
const pointer = ref<{ x: number; y: number } | null>(null)

/**
 * Every movement in the browser arrives here, so this is the
 * one place that knows where the pointer is - and the one place a press turns
 * into a drag, which cannot be the section the tab came from: the pointer
 * leaves it immediately. See G1.
 */
function onPointerMove(event: PointerEvent) {
  props.context.pointerMoved(event.clientX, event.clientY)
  if (props.context.dragging.value !== null) pointer.value = { x: event.clientX, y: event.clientY }
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

function onKeyDown(event: KeyboardEvent) {
  if (event.key === "Escape") onWindowPointerUp()
}

onMounted(() => {
  window.addEventListener("pointermove", onPointerMove)
  window.addEventListener("pointerup", onWindowPointerUp)
  window.addEventListener("pointercancel", onWindowPointerUp)
  window.addEventListener("blur", onWindowPointerUp)
  window.addEventListener("keydown", onKeyDown)
})

onBeforeUnmount(() => {
  window.removeEventListener("pointermove", onPointerMove)
  window.removeEventListener("pointerup", onWindowPointerUp)
  window.removeEventListener("pointercancel", onWindowPointerUp)
  window.removeEventListener("blur", onWindowPointerUp)
  window.removeEventListener("keydown", onKeyDown)
})
</script>

<template>
  <div
    class="workspace"
    data-testid="workspace"
  >
    <WorkspacePanels :context="context">
      <WorkspaceNode :node="context.tree.value" />
      <WorkspaceFloatingWindows :context="context" />
    </WorkspacePanels>

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
  box-sizing: border-box;
  border: 1px solid var(--dp-border-strong);
  border-radius: var(--dp-radius-panel);
  background: var(--dp-surface);
  box-shadow: 0 1px 4px var(--dp-shadow-soft);
}
</style>
