<script setup lang="ts">
import { computed, useTemplateRef } from "vue"

import { AppCardFrame, AppCardHead, AppIconButton } from "@/shared/ui"
import { WorkspaceSeparator } from "@/shared/workspace"

import { BOTTOM_TOOLS } from "./bottomTools"
import { useBottomPanel } from "./useBottomPanel"

/**
 * The panel along the foot of the workspace (D143): a card under whatever
 * space is shown and between the rails, holding one tool at a time. Its
 * height is dragged by the gap above it, as a column's width is by the gap
 * beside it.
 */
const panel = useBottomPanel()
const tool = computed(() => BOTTOM_TOOLS.find((one) => one.id === panel.open.value) ?? null)
const card = useTemplateRef<InstanceType<typeof AppCardFrame>>("card")

// From the height the card is drawn at, not the one stored: the room above
// caps it, and a drag from a stored height past that cap moved nothing for
// the first stretch of the pointer.
function resize(deltaPx: number) {
  const element = card.value?.$el as HTMLElement | undefined
  if (element === undefined) return
  panel.setHeight(element.getBoundingClientRect().height - deltaPx)
}
</script>

<template>
  <template v-if="tool">
    <WorkspaceSeparator
      direction="column"
      @move="resize"
    />
    <AppCardFrame
      ref="card"
      tag="section"
      class="bottom-panel"
      :style="{ height: `${String(panel.height.value)}px` }"
      :aria-label="tool.title"
      data-testid="bottom-panel"
    >
      <AppCardHead :title="tool.title">
        <template #actions>
          <AppIconButton
            icon="remove"
            tooltip="Hide"
            data-testid="bottom-panel-hide"
            @click="panel.hide()"
          />
        </template>
      </AppCardHead>
      <div class="bottom-panel__body">
        <component :is="tool.component" />
      </div>
    </AppCardFrame>
  </template>
</template>

<style scoped>
/* The workspace above keeps room to be worked in whatever height was
   stored: a panel dragged tall in a big window must not bury the columns in
   a small one. */
.bottom-panel {
  flex: none;
  max-height: calc(100% - 160px);
}
.bottom-panel__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--dp-space-2);
}
</style>
