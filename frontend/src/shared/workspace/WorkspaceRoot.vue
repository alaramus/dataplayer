<script setup lang="ts">
import { provide } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import WorkspaceNode from "./WorkspaceNode.vue"

const props = defineProps<{ context: WorkspaceContext }>()

provide(workspaceKey, props.context)

/** A drag released outside every section is a drag that came to nothing. */
function onPointerUp() {
  if (props.context.dragging.value !== null) props.context.endDrag(null, null)
}
</script>

<template>
  <div
    class="workspace"
    data-testid="workspace"
    @pointerup="onPointerUp"
  >
    <WorkspaceNode :node="context.tree.value" />
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
