<script setup lang="ts">
import { computed, inject, ref } from "vue"

import { freshnessTooltip, isLive } from "@/shared/freshness/freshness"
import type { Freshness } from "@/shared/freshness/freshness"
import { useNow } from "@/shared/freshness/useNow"
import { AppIconButton, AppTooltip } from "@/shared/ui"
import { workspaceKey } from "@/shared/workspace"

import { useReloadRegistry } from "./reloadable"
import { workspaceActionsKey } from "./state"

/**
 * What a panel offers about itself, at the end of its own row of commands.
 *
 * Two things that used to be drawn by the chrome around a panel rather than by
 * the panel: the way back to the node in the catalog, which was a click on the
 * icon of the tab, and re-reading, which was a second button on the tab. Both
 * are commands about what the panel is showing, so they sit where every other
 * such command sits (D112).
 *
 * The way out of a window is not one of them. It is about the frame rather
 * than about the rows, so it stands with minimize and close in the window's
 * own bar — which is also where somebody looks for it.
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

/**
 * Whether what is on screen is the read itself or something kept.
 *
 * Counted against the clock rather than fixed when the page arrived: an answer
 * read four minutes ago is not live any more, whatever the server said at the
 * time — and that is the case that made somebody press reload out of doubt.
 */
const now = useNow()
const live = computed(
  () => props.freshness !== undefined && isLive(props.freshness, now.value)
)

/**
 * How old this is, and how long this connection keeps an answer.
 *
 * The mark beside the reload says which of the two states it is in; how old,
 * exactly, is a question rather than a glance, and the answer is on hovering
 * the mark itself. Written on the button it would make a command whose width
 * follows the age of a page, and a row of buttons is read by where its buttons
 * are (D105).
 */
const freshnessSays = computed(() =>
  props.freshness === undefined
    ? ""
    : freshnessTooltip(props.freshness, props.cacheTtlSeconds, now.value)
)

/** The button's own words: how old this is, then what pressing it does. */
const reloadSays = computed(() => {
  const command = reloadTooltip.value ?? ""
  if (props.freshness === undefined) return command
  return `${freshnessSays.value} ${command}.`
})

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
    <!-- Always the same button. What stands beside it changes; the button
         itself does not move, does not change width and does not change what
         pressing it does. -->
    <span
      v-if="reloadTooltip"
      class="panel-commands__reload"
    >
      <AppIconButton
        icon="refresh"
        :tooltip="reloadSays"
        :aria-label="reloadTooltip"
        :loading="reloading"
        data-testid="panel-reload"
        @click="reload"
      />
      <!-- Beside the button and above it, in the flow and not over it: room of
           its own, so nothing is drawn on top of the arrow and nothing after
           it moves. One width for both states, so the row does not shift when
           a read stops being live. Only where the source keeps anything —
           where it does not, an answer cannot be older than the read (D105). -->
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
      icon="my_location"
      tooltip="Show in catalog"
      aria-label="Show in catalog"
      data-testid="panel-reveal"
      @click="showInCatalog"
    />
  </span>
</template>

<style scoped>
.panel-commands {
  display: contents;
}
/* The mark rides at the top of the button rather than beside its middle. */
.panel-commands__reload {
  display: inline-flex;
  align-items: flex-start;
  flex: none;
}
.panel-commands__freshness {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 2px;
  /* One width whichever state it is in, so the row does not move at the moment
     a read stops being live. */
  min-width: 24px;
  margin: 3px 0 0 1px;
  color: var(--dp-text-muted);
  font-size: 9px;
  line-height: 1;
  white-space: nowrap;
  /* A label and not a control: hovering it answers how old this is, pressing
     it does nothing, and it never looks like it would. */
  cursor: default;
}
.panel-commands__freshness--live {
  color: var(--dp-link);
}
</style>
