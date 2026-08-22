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

/** A pinned section with nothing in it: the feature says what stands there. */
const empty = computed(() => (active.value === null ? workspace.emptyOf(props.leaf.accepts ?? null) : null))

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

/** What a collapsed handle says it will bring back. */
const collapsedTitle = computed(() => {
  const first = props.leaf.activePanel ?? props.leaf.panels[0] ?? null
  const title = first === null ? null : workspace.lookOf(first).title
  return props.leaf.collapsed ? `Show ${title ?? "this section"}` : "Hide"
})

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
      <!-- A collapsed section is twenty-eight pixels wide, and a tab strip
           with `overflow: hidden` would push the handle that brings it back
           off the end of it. So a collapsed section shows the handle and
           nothing else. See the spec, S11. -->
      <div
        v-if="!leaf.collapsed"
        class="workspace-leaf__tabs"
      >
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
            v-if="workspace.lookOf(panelId).closable !== false"
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
      </div>

      <button
        v-if="collapsible"
        type="button"
        class="workspace-leaf__collapse"
        :title="collapsedTitle"
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
      <!-- A tab that is not showing is kept rather than destroyed: switching
           away and back is not a reason to re-read a catalog or to lose the
           page a grid was on, which is what a plain <component :is> would
           do. -->
      <KeepAlive v-if="active !== null">
        <component
          :is="workspace.componentOf(active)"
          :key="active"
        />
      </KeepAlive>

      <component
        :is="empty"
        v-else-if="empty"
      />
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
/* The tabs give way, the handle never does: a narrow section loses the end of
   a tab title rather than the button that collapses it. */
.workspace-leaf__tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
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
.workspace-leaf__collapse {
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 2px;
  margin-left: auto;
  flex: none;
}
/* A box of fixed height, not a scroller: what stands and what moves inside a
   panel is the panel's own business — the engine has no notion of a panel
   header to keep still. See the spec, S10. */
.workspace-leaf__body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.workspace-leaf__overlay {
  /* Purely a visual drop-target hint: the leaf's own pointerup/pointermove
     handlers do the real work, and this sits on top of the whole leaf
     (tab strip included). Without pointer-events: none it swallows the
     pointerup/click of whatever it happens to cover the instant a tab
     press starts a drag - which included the close button on its own tab. */
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.workspace-leaf__zone {
  background: rgba(25, 118, 210, 0.18);
  border: 2px solid rgba(25, 118, 210, 0.6);
  border-radius: 4px;
}
</style>
