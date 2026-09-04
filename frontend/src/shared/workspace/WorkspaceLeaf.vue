<script setup lang="ts">
import { computed, inject, ref } from "vue"
import type { CSSProperties } from "vue"

import AppTooltip from "@/shared/ui/AppTooltip.vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { dropShape, dropZoneFor, insertionAt } from "./dropZone"
import type { SectionRects } from "./dropZone"
import type { DropZone, LeafNode } from "./model"
import WorkspacePanelTarget from "./WorkspacePanelTarget.vue"

const props = defineProps<{ leaf: LeafNode; collapsible: boolean }>()

const injected = inject(workspaceKey)
if (injected === undefined) throw new Error("WorkspaceLeaf used outside a WorkspaceRoot")
// Narrowing a const across `if (x === undefined) throw` does not survive into
// a later function declaration or into the template's own render function -
// restating the type here, once, means every use below is never undefined
// rather than every use needing its own guard.
const workspace: WorkspaceContext = injected

/**
 * Which tabs of this section are re-reading themselves right now.
 *
 * Per tab and not one flag: two tabs of one section can be told to reload, and
 * a single flag would spin both buttons and unlock both on the first answer.
 */
const reloading = ref<Set<string>>(new Set())

async function onReload(panelId: string) {
  if (reloading.value.has(panelId)) return
  reloading.value = new Set(reloading.value).add(panelId)
  try {
    await workspace.onReload?.(panelId)
  } finally {
    const left = new Set(reloading.value)
    left.delete(panelId)
    reloading.value = left
  }
}

const element = ref<HTMLElement | null>(null)
const stripElement = ref<HTMLElement | null>(null)
const zone = ref<DropZone | null>(null)
/**
 * Where in this strip the tab would land, while it is being held over it.
 *
 * Null while nothing is over the strip. An index otherwise, including one past
 * the last tab, and the mark is drawn there: a tab dropped anywhere in the
 * strip used to go to the end however carefully it was aimed, which made half
 * the gesture pointless.
 */
const insertion = ref<number | null>(null)
const tabElements = ref<HTMLElement[]>([])
/** Measured while the pointer is over the section, and only used to draw. */
const stripHeight = ref(0)

const active = computed(() => props.leaf.activePanel)

/**
 * The tabs that are drawn. The one being dragged is in the user's hand, and
 * leaving a copy of it in the strip is what made the gesture unreadable.
 * See G2.
 */
const shownTabs = computed(() =>
  props.leaf.panels.filter((panelId) => panelId !== workspace.dragging.value)
)

/** A pinned section with nothing in it: the feature says what stands there. */
const empty = computed(() => (active.value === null ? workspace.emptyOf(props.leaf.accepts ?? null) : null))

/**
 * What a collapsed section keeps on screen, if the feature offers anything.
 *
 * Asked of the panel that would be showing: a column pushed aside can still be
 * worth reaching - a strip of connections is a way back into one of them - and
 * what deserves that width is not the engine's to decide.
 */
const collapsedBody = computed(() =>
  active.value === null ? null : workspace.collapsedOf(active.value)
)

/** A cross closes one tab; this closes the rest. */
const closableOthers = computed(
  () =>
    props.leaf.panels.filter(
      (panelId) => panelId !== active.value && workspace.lookOf(panelId).closable !== false
    ).length
)

/**
 * The section as a drop target: the strip and the body, measured now.
 *
 * Not a computed, for the reason WorkspaceNode gives about its own length:
 * a rectangle is not reactive, so a memoised one would answer with where the
 * section used to be.
 */
function rects(): SectionRects | null {
  if (element.value === null) return null
  const leaf = element.value.getBoundingClientRect()
  const height = stripElement.value?.getBoundingClientRect().height ?? 0
  stripHeight.value = height
  return {
    strip: { left: leaf.left, top: leaf.top, width: leaf.width, height },
    body: {
      left: leaf.left,
      top: leaf.top + height,
      width: leaf.width,
      height: leaf.height - height,
    },
  }
}

function onPointerMove(event: PointerEvent) {
  if (workspace.dragging.value === null) {
    zone.value = null
    insertion.value = null
    return
  }
  const measured = rects()
  if (measured === null) return
  // Null for a section that refuses what is being dragged, and the overlay
  // draws nothing for null: the only thing this screen says about a refusal
  // is that it does not offer. See P1.
  zone.value = dropZoneFor(
    measured,
    event.clientX,
    event.clientY,
    workspace.admissionOf(props.leaf.id)
  )
  // Measured now rather than kept: the tabs move as one of them is taken out
  // of the strip, and a remembered rectangle would mark where a tab used to be.
  insertion.value =
    zone.value === "center"
      ? insertionAt(
          tabElements.value.map((tab) => tab.getBoundingClientRect()),
          event.clientX
        )
      : null
}

function onPointerUp() {
  // Unconditional: a press that never became a drag is forgotten here too,
  // or the next movement of the pointer would begin one with no button held.
  workspace.endDrag(props.leaf.id, zone.value, insertion.value ?? undefined)
  zone.value = null
  insertion.value = null
}

/**
 * Pressing a tab begins a possible drag, and nothing else. It becomes one only
 * once the pointer has moved far enough to mean it - see G1. Activating is
 * left to the click that follows a press which did not become a drag, which is
 * also what lets the keyboard reach a tab, since Enter on a button raises
 * click and never pointerdown.
 */
function onTabPointerDown(event: PointerEvent, panelId: string) {
  if (event.button !== 0) return
  workspace.focus(props.leaf.id)
  workspace.press(panelId, event.clientX, event.clientY)
}

/** What a collapsed handle says it will bring back. */
const collapsedTitle = computed(() => {
  const first = props.leaf.activePanel ?? props.leaf.panels[0] ?? null
  const title = first === null ? null : workspace.lookOf(first).title
  return props.leaf.collapsed ? `Show ${title ?? "this section"}` : "Hide"
})

/** What will be lit: where the panel ends up, not which zone the pointer is in. */
const shape = computed(() => dropShape(zone.value, props.leaf.panels.length === 0))

const overlayStyle = computed((): CSSProperties => {
  if (shape.value === "none") return { display: "none" }
  if (shape.value === "strip") {
    // The head of the section, exactly as tall as it is drawn: the panel joins
    // the tabs, so the tabs are what lights up.
    return {
      position: "absolute",
      left: "0",
      top: "0",
      width: "100%",
      height: `${String(stripHeight.value)}px`,
    }
  }
  const box: Record<DropZone, Record<string, string>> = {
    left: { left: "0", top: "0", width: "50%", height: "100%" },
    right: { left: "50%", top: "0", width: "50%", height: "100%" },
    top: { left: "0", top: "0", width: "100%", height: "50%" },
    bottom: { left: "0", top: "50%", width: "100%", height: "50%" },
    center: { left: "0", top: "0", width: "100%", height: "100%" },
  }
  return { position: "absolute", ...box[zone.value ?? "center"] }
})
</script>

<template>
  <div
    ref="element"
    class="workspace-leaf"
    :data-testid="`workspace-leaf-${leaf.id}`"
    @pointerdown="workspace.focus(leaf.id)"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointerleave="zone = null; insertion = null"
  >
    <div
      ref="stripElement"
      class="workspace-leaf__strip"
    >
      <!-- A collapsed section is twenty-eight pixels wide, and a tab strip
           with `overflow: hidden` would push the handle that brings it back
           off the end of it. So a collapsed section shows the handle and
           nothing else. See the spec, S11. -->
      <div
        v-if="!leaf.collapsed"
        class="workspace-leaf__tabs"
      >
        <template
          v-for="(panelId, index) in shownTabs"
          :key="panelId"
        >
          <!-- Where the tab in the hand would land. Drawn before the tab it
               would come before, and after the last one when it goes at the
               end, so the strip says what the release will do. -->
          <span
            v-if="insertion === index"
            class="workspace-leaf__insertion"
            data-testid="workspace-tab-insertion"
          />
          <button
            ref="tabElements"
            type="button"
            class="workspace-leaf__tab"
            :class="{ 'workspace-leaf__tab--active': panelId === active }"
            :data-testid="`workspace-tab-${panelId}`"
            @pointerdown="onTabPointerDown($event, panelId)"
            @click="workspace.activate(panelId)"
          >
            <span
              v-if="workspace.lookOf(panelId).iconTooltip && workspace.onIconClick"
              class="workspace-leaf__icon workspace-leaf__icon--action"
              :data-testid="`workspace-tab-icon-${panelId}`"
              role="button"
              tabindex="0"
              @click.stop="workspace.onIconClick?.(panelId)"
              @keydown.enter.stop="workspace.onIconClick?.(panelId)"
              @keydown.space.stop.prevent="workspace.onIconClick?.(panelId)"
              @pointerdown.stop
            >
              <q-icon
                :name="workspace.lookOf(panelId).icon"
                size="16px"
              />
              <AppTooltip>{{ workspace.lookOf(panelId).iconTooltip }}</AppTooltip>
            </span>
            <q-icon
              v-else
              :name="workspace.lookOf(panelId).icon"
              size="16px"
            />
            <span class="workspace-leaf__title">{{ workspace.lookOf(panelId).title }}</span>
            <span
              v-if="workspace.lookOf(panelId).subtitle"
              class="workspace-leaf__subtitle"
            >{{ workspace.lookOf(panelId).subtitle }}</span>
            <span
              v-if="workspace.lookOf(panelId).reloadTooltip && workspace.onReload"
              class="workspace-leaf__reload"
              :class="{ 'workspace-leaf__reload--busy': reloading.has(panelId) }"
              :data-testid="`workspace-reload-${panelId}`"
              role="button"
              tabindex="0"
              @click.stop="onReload(panelId)"
              @keydown.enter.stop="onReload(panelId)"
              @keydown.space.stop.prevent="onReload(panelId)"
              @pointerdown.stop
            >
              <q-icon
                name="refresh"
                size="14px"
              />
              <AppTooltip>{{ workspace.lookOf(panelId).reloadTooltip }}</AppTooltip>
            </span>
            <span
              v-if="workspace.lookOf(panelId).closable !== false"
              class="workspace-leaf__close"
              :data-testid="`workspace-close-${panelId}`"
              @click.stop="workspace.requestClose(panelId)"
            >
              <q-icon
                name="close"
                size="14px"
              />
            </span>
          </button>
        </template>
        <!-- And the last place of all, which no tab comes before. -->
        <span
          v-if="insertion === shownTabs.length && shownTabs.length > 0"
          class="workspace-leaf__insertion"
          data-testid="workspace-tab-insertion"
        />
      </div>

      <button
        v-if="!leaf.collapsed && closableOthers > 0"
        type="button"
        class="workspace-leaf__collapse"
        :data-testid="`workspace-close-others-${leaf.id}`"
        @click="workspace.closeOthers(leaf.id)"
      >
        <q-icon
          name="clear_all"
          size="16px"
        />
        <AppTooltip>Close the other tabs</AppTooltip>
      </button>

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
        <AppTooltip>{{ collapsedTitle }}</AppTooltip>
      </button>
    </div>

    <!-- Collapsed, and the feature had something for that width. -->
    <div
      v-if="leaf.collapsed"
      class="workspace-leaf__rail"
    >
      <component
        :is="collapsedBody"
        v-if="collapsedBody"
      />
    </div>

    <WorkspacePanelTarget
      v-else
      class="workspace-leaf__body"
      :target-id="leaf.id"
      :panel-id="active"
    >
      <component
        :is="empty"
        v-if="empty"
      />
    </WorkspacePanelTarget>

    <div
      v-if="workspace.dragging.value !== null"
      class="workspace-leaf__overlay"
      data-testid="workspace-dropzone"
    >
      <div
        class="workspace-leaf__zone"
        :class="`workspace-leaf__zone--${shape}`"
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
  background: var(--dp-surface);
}
.workspace-leaf__strip {
  display: flex;
  align-items: flex-start;
  gap: 2px;
  padding: 2px var(--dp-space-1);
  border-bottom: 1px solid var(--dp-border);
  background: var(--dp-chrome-raised);
  /* The head of a column is one height whatever stands in it: a column with a
     tab beside one with only its handles put the line under them at two
     different heights, which reads as a broken layout rather than as an empty
     one. A floor and not a fixed height, because tabs still wrap onto a
     second line. */
  min-height: var(--dp-tab-strip-height);
}
/* Tabs wrap onto a second line rather than running off the end of the strip:
   a tab that cannot be seen cannot be reached, and a section is only ever as
   wide as the column it is in. The handles keep their place at the end
   because they are laid out beside the whole block of tabs, not inside it. */
.workspace-leaf__tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}
/* Where the tab would land: a line between two tabs, the same colour the drop
   zone of a whole section is outlined with. */
.workspace-leaf__insertion {
  flex: none;
  align-self: stretch;
  width: 2px;
  margin: 2px 0;
  border-radius: 1px;
  background: var(--dp-dropzone-border);
}

.workspace-leaf__tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: none;
  border-radius: var(--dp-radius-control);
  background: transparent;
  /* A native button takes its colour from the browser, which is black, and
     `font: inherit` does not carry colour with it. Black on a dark panel is
     an invisible tab. */
  color: inherit;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.workspace-leaf__tab--active {
  background: var(--dp-surface);
  box-shadow: inset 0 0 0 1px var(--dp-border);
  font-weight: 500;
}
.workspace-leaf__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.workspace-leaf__icon--action {
  cursor: pointer;
  border-radius: 4px;
  padding: 2px;
  margin: -2px;
}
.workspace-leaf__icon--action:hover {
  background: var(--dp-hover);
}
/* Beside the cross, and always drawn: reserving the room only on hover would
   move the title under the pointer the moment it arrives. */
.workspace-leaf__reload {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  cursor: pointer;
  border-radius: 4px;
  padding: 2px;
  margin: -2px;
  color: var(--dp-text-faint);
}
.workspace-leaf__reload:hover {
  background: var(--dp-hover);
  color: inherit;
}
/* Working: the same button, turning. A separate spinner would change the width
   of the tab at the moment it is being pressed. */
.workspace-leaf__reload--busy {
  cursor: default;
  pointer-events: none;
  animation: workspace-leaf-turn 900ms linear infinite;
}
@keyframes workspace-leaf-turn {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .workspace-leaf__reload--busy {
    animation: none;
    opacity: 0.5;
  }
}
.workspace-leaf__title {
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}
/* Whose tab this is. It goes first when the room runs out: the name of the
   node is what is being looked for, and this only tells two alike apart. */
.workspace-leaf__subtitle {
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  max-width: 96px;
  color: var(--dp-text-faint);
}
/* The tabs take the room, so the handles sit at the end without a margin of
   their own - which two of them beside each other would fight over. */
.workspace-leaf__collapse {
  border: none;
  background: transparent;
  /* The icon inside draws itself in currentColor - see the tab above. */
  color: inherit;
  cursor: pointer;
  padding: 2px;
  flex: none;
}
.workspace-leaf__rail {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
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
  /* Over everything the panel draws, a sticky table heading included: a
     heading declares a layer of its own, so an overlay that declared none was
     painted over by it and the column names stood outside the drop zone.
     What each layer is worth is in `shared/ui/layers.css`. */
  z-index: var(--dp-layer-overlay);
}
.workspace-leaf__zone {
  background: var(--dp-dropzone);
  border: 2px solid var(--dp-dropzone-border);
  border-radius: 4px;
}
</style>
