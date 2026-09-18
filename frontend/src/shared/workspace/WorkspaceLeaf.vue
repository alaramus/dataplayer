<script setup lang="ts">
import { computed, inject, ref } from "vue"
import type { CSSProperties } from "vue"

import AppTooltip from "@/shared/ui/AppTooltip.vue"
import { panelColorStyle } from "@/shared/ui/panelColor"

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

/**
 * What this section is showing, which is nothing while it is on the bar.
 *
 * A section put aside keeps its panels and its active tab — that is what
 * bringing it back restores — so the whole of "it is not on the screen" lives
 * here: no tabs, no body, and whatever the feature stands in an empty column
 * takes its place (the column of work says what can be opened in it; a column
 * with nothing to say is not drawn at all, see `visibility.ts`).
 */
const active = computed(() => (props.leaf.minimized === true ? null : props.leaf.activePanel))

/**
 * The tabs that are drawn. The one being dragged is in the user's hand, and
 * leaving a copy of it in the strip is what made the gesture unreadable.
 * See G2.
 */
const shownTabs = computed(() =>
  props.leaf.minimized === true
    ? []
    : props.leaf.panels.filter((panelId) => panelId !== workspace.dragging.value)
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
    shownTabs.value.filter(
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

/**
 * What the head of this section offers: to narrow it, to put it aside, or
 * nothing at all.
 *
 * Read off what is already known rather than off the role, which the engine
 * does not read (D12). A section holding nothing is a column that exists to
 * say what could be opened in it — pushing that aside leaves the screen
 * saying less and nothing gained, so it offers neither gesture. A section
 * whose panel has something worth forty pixels narrows to those forty; one
 * that has not is put on the bar whole, because forty pixels of empty strip
 * is room spent on a handle.
 */
const handle = computed<"collapse" | "aside" | "none">(() => {
  if (!props.collapsible) return "none"
  const panel = active.value
  if (panel === null) return "none"
  if (workspace.collapsedOf(panel) !== null) {
    // The feature's chrome owns the first section's chevron (the application
    // header): a second button for the same gesture would only double it.
    if (workspace.hideFirstCollapse && workspace.firstLeafId.value === props.leaf.id) return "none"
    return "collapse"
  }
  return workspace.sectionLookOf(props.leaf.accepts ?? null) === null ? "collapse" : "aside"
})

/** What the bar will call this section once it is on it. */
const asideTitle = computed(
  () => workspace.sectionLookOf(props.leaf.accepts ?? null)?.title ?? "this section"
)

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
      v-if="!leaf.collapsed || handle !== 'none'"
      ref="stripElement"
      class="workspace-leaf__strip"
    >
      <!-- A collapsed section is twenty-eight pixels wide, and a tab strip
           with `overflow: hidden` would push the handle that brings it back
           off the end of it. So a collapsed section shows the handle and
           nothing else. See the spec, S11. Where the feature owns that
           handle itself, the strip stands down wholly and only the rail
           below remains. -->
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
          <div
            ref="tabElements"
            role="button"
            tabindex="0"
            :aria-label="workspace.lookOf(panelId).title"
            class="workspace-leaf__tab"
            :class="{ 'workspace-leaf__tab--active': panelId === active }"
            :style="panelColorStyle(workspace.lookOf(panelId).color)"
            :data-testid="`workspace-tab-${panelId}`"
            @pointerdown="onTabPointerDown($event, panelId)"
            @click="workspace.activate(panelId)"
            @keydown.enter.self.prevent="workspace.activate(panelId)"
            @keydown.space.self.prevent="workspace.activate(panelId)"
          >
            <!-- A button only where pressing it reaches something the panel's
                 own row of commands cannot — the connection behind a catalog.
                 Everywhere else this is an icon with hover text, because an
                 icon drawn as a button wherever it had a tooltip is how four
                 kinds came to offer a press that did nothing. See D112. -->
            <span
              v-if="workspace.lookOf(panelId).iconCommand && workspace.onIconClick"
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
            <span
              v-else
              class="workspace-leaf__icon"
              :data-testid="`workspace-tab-icon-${panelId}`"
            >
              <q-icon
                :name="workspace.lookOf(panelId).icon"
                size="16px"
              />
              <AppTooltip v-if="workspace.lookOf(panelId).iconTooltip">
                {{ workspace.lookOf(panelId).iconTooltip }}
              </AppTooltip>
            </span>
            <span class="workspace-leaf__title">{{ workspace.lookOf(panelId).title }}</span>
            <span
              v-if="workspace.lookOf(panelId).subtitle"
              class="workspace-leaf__subtitle"
            >{{ workspace.lookOf(panelId).subtitle }}</span>
            <span
              v-if="workspace.lookOf(panelId).closable !== false"
              class="workspace-leaf__close"
              :data-testid="`workspace-close-${panelId}`"
              role="button"
              tabindex="0"
              :aria-label="`Close ${workspace.lookOf(panelId).title}`"
              @click.stop="workspace.requestClose(panelId)"
              @keydown.enter.stop.prevent="workspace.requestClose(panelId)"
              @keydown.space.stop.prevent="workspace.requestClose(panelId)"
              @pointerdown.stop
            >
              <q-icon
                name="close"
                size="14px"
              />
            </span>
          </div>
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
        v-if="handle === 'collapse'"
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

      <!-- Off the screen and onto the bar, the gesture a window has. -->
      <button
        v-else-if="handle === 'aside'"
        type="button"
        class="workspace-leaf__collapse"
        :data-testid="`workspace-aside-${leaf.id}`"
        :aria-label="`Put ${asideTitle} aside`"
        @click="workspace.putAside(leaf.id)"
      >
        <q-icon
          name="minimize"
          size="16px"
        />
        <AppTooltip>Put {{ asideTitle }} aside</AppTooltip>
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
/* A card: its own ground, its own edge, its own corners. What separates two
   of them is the space between, which is also what is dragged to resize
   them — see WorkspaceSeparator. The same frame as AppCardFrame, written out
   here because this root carries the drag handlers and is measured. */
.workspace-leaf {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  box-sizing: border-box;
  /* Changing this changes --dp-workspace-card-edges, which counts it. */
  border: 1px solid var(--dp-border);
  border-radius: var(--dp-radius-panel);
  background: var(--dp-surface);
}
.workspace-leaf__strip {
  display: flex;
  align-items: flex-start;
  gap: 2px;
  padding: 2px var(--dp-space-1);
  /* The head every card has (AppCardHead). */
  border-bottom: 1px solid var(--dp-border);
  background: var(--dp-card-head);
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

/* One shape for every tab. A connection with no colour of its own is drawn
   in the plain one rather than in no colour at all: whether somebody has
   chosen a colour is not something the size and form of a tab should say, and
   a strip of half-filled and half-transparent tabs read as two kinds of
   thing. The colour is the only difference the choice makes, and the plain
   fill is the same one a row of the connections carries. */
.workspace-leaf__tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: none;
  border-radius: var(--dp-radius-control);
  background: var(--dp-panel-background, var(--dp-panel-plain));
  /* A native button takes its colour from the browser, which is black, and
     `font: inherit` does not carry colour with it. Black on a dark panel is
     an invisible tab. */
  color: var(--dp-panel-foreground, inherit);
  font: inherit;
  font-size: 12px;
  /* The same weight whether or not this is the tab being read: bold text is
     wider, so a weight that changed with the state moved every tab beside it
     at the moment one was pressed. What marks the active one is the line
     under it, which costs no room. */
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  /* A tab drag must not select text and turn the next drag into a native one. */
  user-select: none;
}
.workspace-leaf__tab--active {
  box-shadow: inset 0 -3px currentColor;
}
.workspace-leaf__tab:focus-visible,
.workspace-leaf__close:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
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
  color: var(--dp-panel-foreground, var(--dp-text-faint));
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
