<script setup lang="ts">
import { computed, inject, ref } from "vue"
import type { CSSProperties } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { dropZoneAt } from "./dropZone"
import type { DropZone, LeafNode } from "./model"

const props = defineProps<{ leaf: LeafNode; collapsible: boolean }>()

const injected = inject(workspaceKey)
if (injected === undefined) throw new Error("WorkspaceLeaf used outside a WorkspaceRoot")
// Narrowing a const across `if (x === undefined) throw` does not survive into
// a later function declaration or into the template's own render function -
// restating the type here, once, means every use below is never undefined
// rather than every use needing its own guard.
const workspace: WorkspaceContext = injected

const element = ref<HTMLElement | null>(null)
const zone = ref<DropZone | null>(null)

const active = computed(() => props.leaf.activePanel)

function onPointerMove(event: PointerEvent) {
  if (workspace.dragging.value === null || element.value === null) return
  zone.value = dropZoneAt(element.value.getBoundingClientRect(), event.clientX, event.clientY)
}

function onPointerUp() {
  if (workspace.dragging.value === null) return
  workspace.endDrag(props.leaf.id, zone.value)
  zone.value = null
}

/**
 * Pressing a tab begins a possible drag, and nothing else. Activating is left
 * to the click that follows a press which did not become one - which is also
 * what lets the keyboard reach a tab, since Enter on a button raises click and
 * never pointerdown.
 */
function onTabPointerDown(panelId: string) {
  workspace.focus(props.leaf.id)
  workspace.startDrag(panelId)
}

const overlayStyle = computed((): CSSProperties => {
  const box: Record<DropZone, Record<string, string>> = {
    left: { left: "0", top: "0", width: "50%", height: "100%" },
    right: { left: "50%", top: "0", width: "50%", height: "100%" },
    top: { left: "0", top: "0", width: "100%", height: "50%" },
    bottom: { left: "0", top: "50%", width: "100%", height: "50%" },
    center: { left: "0", top: "0", width: "100%", height: "100%" },
  }
  return zone.value === null ? { display: "none" } : { position: "absolute", ...box[zone.value] }
})
</script>

<template>
  <div
    ref="element"
    class="workspace-leaf"
    :data-testid="`workspace-leaf-${leaf.id}`"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
  >
    <div class="workspace-leaf__strip">
      <button
        v-for="panelId in leaf.panels"
        :key="panelId"
        type="button"
        class="workspace-leaf__tab"
        :class="{ 'workspace-leaf__tab--active': panelId === active }"
        :data-testid="`workspace-tab-${panelId}`"
        @pointerdown="onTabPointerDown(panelId)"
        @click="workspace.activate(panelId)"
      >
        <q-icon
          :name="workspace.lookOf(panelId).icon"
          size="16px"
        />
        <span class="workspace-leaf__title">{{ workspace.lookOf(panelId).title }}</span>
        <span
          class="workspace-leaf__close"
          :data-testid="`workspace-close-${panelId}`"
          @click.stop="workspace.close(panelId)"
        >
          <q-icon
            name="close"
            size="14px"
          />
        </span>
      </button>

      <span class="workspace-leaf__spacer" />

      <button
        v-if="collapsible"
        type="button"
        class="workspace-leaf__collapse"
        :data-testid="`workspace-collapse-${leaf.id}`"
        @click="workspace.toggleCollapse(leaf.id)"
      >
        <q-icon
          :name="leaf.collapsed ? 'chevron_right' : 'chevron_left'"
          size="16px"
        />
      </button>
    </div>

    <div
      v-if="!leaf.collapsed"
      class="workspace-leaf__body"
    >
      <component :is="workspace.componentOf(active)" />
    </div>

    <div
      v-if="workspace.dragging.value !== null"
      class="workspace-leaf__overlay"
      data-testid="workspace-dropzone"
    >
      <div
        class="workspace-leaf__zone"
        :style="overlayStyle"
      />
    </div>
  </div>
</template>

<style scoped>
.workspace-leaf {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: #fff;
}
.workspace-leaf__strip {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
  overflow: hidden;
}
.workspace-leaf__tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: none;
  border-radius: 4px 4px 0 0;
  background: transparent;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.workspace-leaf__tab--active {
  background: rgba(0, 0, 0, 0.06);
  font-weight: 500;
}
.workspace-leaf__title {
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}
.workspace-leaf__spacer {
  flex: 1;
}
.workspace-leaf__collapse {
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 2px;
}
.workspace-leaf__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.workspace-leaf__overlay {
  position: absolute;
  inset: 0;
}
.workspace-leaf__zone {
  background: rgba(25, 118, 210, 0.18);
  border: 2px solid rgba(25, 118, 210, 0.6);
  border-radius: 4px;
}
</style>
