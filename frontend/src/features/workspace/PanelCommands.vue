<script setup lang="ts">
import { computed, inject, ref } from "vue"

import { AppIconButton } from "@/shared/ui"
import { workspaceKey } from "@/shared/workspace"

import { useReloadRegistry } from "./reloadable"
import { workspaceActionsKey } from "./state"

/**
 * What a panel offers about itself, at the end of its own row of commands.
 *
 * Three things that used to be drawn by the chrome around a panel rather than
 * by the panel: the way back to the node in the catalog, which was a click on
 * the icon of the tab; re-reading, which was a second button on the tab; and
 * the way out of a window, which was a strip of its own above a panel that
 * already draws a row of buttons. All three are commands about what the panel
 * is showing, so they sit where every other such command sits (D112).
 *
 * A panel mounted outside the workspace — every panel has a unit test that
 * does exactly that — has no tab to return to and no look to read, so this
 * draws nothing at all there rather than half of itself.
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
}>()

const workspace = inject(workspaceKey, null)
const actions = inject(workspaceActionsKey, null)
const reloads = useReloadRegistry()

/** What the reload button says, and whether this panel offers one at all. */
const reloadTooltip = computed(() =>
  workspace === null ? undefined : workspace.lookOf(props.panelId).reloadTooltip
)

/** In a window of its own, and so with a way back to offer. */
const detached = computed(
  () => workspace?.detached.value.some((one) => one.panelId === props.panelId) === true
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

function dockHere() {
  workspace?.dock(props.panelId)
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
    <AppIconButton
      v-if="reveal && actions"
      icon="my_location"
      tooltip="Show in catalog"
      aria-label="Show in catalog"
      data-testid="panel-reveal"
      @click="showInCatalog"
    />
    <AppIconButton
      v-if="reloadTooltip"
      icon="refresh"
      :tooltip="reloadTooltip"
      :aria-label="reloadTooltip"
      :loading="reloading"
      data-testid="panel-reload"
      @click="reload"
    />
    <!-- Last, so that tearing a panel off and putting it back does not move
         the buttons beside it: this one appears and disappears at the end of
         the row rather than in front of the others. -->
    <AppIconButton
      v-if="detached"
      icon="tab"
      tooltip="Return to panel"
      aria-label="Return to panel"
      data-testid="dock-panel"
      @click="dockHere"
    />
  </span>
</template>

<style scoped>
.panel-commands {
  display: contents;
}
</style>
