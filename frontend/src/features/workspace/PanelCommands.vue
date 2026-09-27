<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, inject, ref } from "vue"

import { freshnessTooltip, isLive } from "@/shared/freshness/freshness"
import type { Freshness } from "@/shared/freshness/freshness"
import { useNow } from "@/shared/freshness/useNow"
import { AppIconButton, AppTooltip } from "@/shared/ui"
import { workspaceKey } from "@/shared/workspace"

import { useReloadRegistry } from "./reloadable"
import { workspaceActionsKey } from "./state"

/**
 * What a panel offers about itself, at the end of its own row of commands
 * (D112): the way back to its node in the catalog, re-reading, and the way
 * into a window of its own and back (D93).
 *
 * Draws nothing when mounted outside the workspace, which every panel's own
 * unit test does: there is no look to read there.
 */
const props = defineProps<{
  panelId: string
  /**
   * The node this panel is a view of, where it is a view of one.
   *
   * Absent for a panel with no place in a catalog: a chart is drawn from a
   * page of rows, a console is written against a connection, a captured
   * result outlives the query that made it. Those show no button rather than
   * one that does nothing.
   */
  reveal?: { connectorId: string; nodeId: string; label: string }
  /**
   * Where what is on screen came from, for a source that keeps its answers.
   *
   * Absent where an answer could not be older than the read — a source that
   * never opted into caching, or an owner who chose to keep nothing — and the
   * reload then stands alone, with nothing to report (D105).
   */
  freshness?: Freshness
  /** What this connection was told to keep, when its owner chose (D105). */
  cacheTtlSeconds?: number | null
}>()

const workspace = inject(workspaceKey, null)
const actions = inject(workspaceActionsKey, null)
const reloads = useReloadRegistry()

/** What the reload button says, and whether this panel offers one at all. */
const reloadTooltip = computed(() =>
  workspace === null ? undefined : workspace.lookOf(props.panelId).reloadTooltip
)

/** Counted against the clock, not fixed when the page arrived: see isLive. */
const now = useNow()
const live = computed(
  () => props.freshness !== undefined && isLive(props.freshness, now.value)
)

/**
 * How old this is. Never drawn in the row: a control whose width follows the
 * age of a page moves while the row is being read (D105).
 */
const freshnessSays = computed(() =>
  props.freshness === undefined
    ? ""
    : freshnessTooltip(props.freshness, props.cacheTtlSeconds, now.value)
)

const reloading = ref(false)

async function reload() {
  if (reloading.value) return
  reloading.value = true
  try {
    await reloads?.reload(props.panelId)
  } finally {
    reloading.value = false
  }
}

/** Where this panel is, if it is in a window rather than a column. */
const floating = computed(() =>
  workspace?.detached.value.find((entry) => entry.panelId === props.panelId)
)

/**
 * Only where the panel is in a column it could leave. The column of
 * connections never leaves the workspace, and a panel of no node has no Show
 * in catalog for the same reason: a command that could never be used there is
 * not one to learn the place of. In a window the way back is the window's own
 * Return to panel, beside minimize and close; a second one here only repeated
 * it.
 */
const offersWindow = computed(() =>
  workspace?.lookOf(props.panelId).closable !== false && floating.value === undefined
)
const mayDetach = computed(() => workspace?.canDetach(props.panelId) === true)

function openWindow() {
  if (workspace !== null && mayDetach.value) workspace.detach(props.panelId)
}

function showInCatalog() {
  const target = props.reveal
  if (target === undefined || actions === null) return
  actions.revealInCatalog(target.connectorId, target.nodeId, target.label)
}
</script>

<template>
  <!-- `display: contents`, so the buttons join the row they are dropped into
       rather than forming a group of their own inside it: the gaps a toolbar
       sets between its buttons then hold across the join. -->
  <span
    v-if="workspace !== null"
    class="panel-commands"
  >
    <!-- The button never changes; only the mark beside it does. -->
    <span
      v-if="reloadTooltip"
      class="panel-commands__reload"
    >
      <AppIconButton
        :icon="appIcons.refresh"
        :tooltip="reloadTooltip"
        :aria-label="reloadTooltip"
        :loading="reloading"
        data-testid="panel-reload"
        @click="reload"
      />
      <!-- In the flow and not over the button: room of its own, one width in
           both states, so nothing is drawn on the arrow and nothing moves when
           a read stops being live. Absent where the source keeps nothing, as
           an answer cannot then be older than the read (D105). -->
      <span
        v-if="freshness"
        class="panel-commands__freshness"
        :class="{ 'panel-commands__freshness--live': live }"
        data-testid="panel-freshness"
        :data-live="live ? 'yes' : 'no'"
      >
        <template v-if="live">Live</template>
        <q-icon
          v-else
          name="schedule"
          size="11px"
        />
        <AppTooltip>{{ freshnessSays }}</AppTooltip>
      </span>
    </span>
    <AppIconButton
      v-if="reveal && actions"
      :icon="appIcons.myLocation"
      tooltip="Show in catalog"
      aria-label="Show in catalog"
      data-testid="panel-reveal"
      @click="showInCatalog"
    />
    <AppIconButton
      v-if="offersWindow"
      :icon="appIcons.window"
      :tooltip="mayDetach ? 'Open in a window' : 'Open in a window — this tab stays in its column'"
      :disable="!mayDetach"
      data-testid="panel-window"
      @click="openWindow"
    />
  </span>
</template>

<style scoped>
.panel-commands {
  display: contents;
}
.panel-commands__reload {
  display: inline-flex;
  align-items: flex-start;
  flex: none;
}
.panel-commands__freshness {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: var(--dp-space-half);
  /* One width in both states, so the row does not move. */
  min-width: 24px;
  margin: var(--dp-space-half) 0 0 1px;
  color: var(--dp-text-muted);
  font-size: 9px;
  line-height: 1;
  white-space: nowrap;
  /* A label, not a control: it presses to nothing and must not look otherwise. */
  cursor: default;
}
.panel-commands__freshness--live {
  color: var(--dp-link);
}
</style>
