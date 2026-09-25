<script setup lang="ts">
import { defineComponent, h, inject, onBeforeUnmount, provide, watch } from "vue"

import { appIcons } from "@/shared/ui"
import { useWindowManager } from "@/shared/windows"
import { panelTargetsKey, workspaceKey } from "@/shared/workspace"

import PairWindow from "./PairWindow.vue"
import { pairTitle } from "./pairs"
import type { PairsApi } from "./usePairs"

/**
 * One window per open pair (D167), drawn inside the workspace's panel host so
 * that the two catalog panels can be sent into it, as `WorkspaceFloatingWindows`
 * does for a panel torn off alone.
 */
const props = defineProps<{ pairs: PairsApi }>()
const manager = useWindowManager()
const targets = inject(panelTargetsKey)
const workspace = inject(workspaceKey)
const opened = new Set<string>()

const windowIdOf = (pairId: string) => `pair:${pairId}`

if (targets !== undefined) {
  const registry = targets
  watch(
    () => props.pairs.pairs.value.map((pair) => ({ id: pair.id, title: pairTitle(pair) })),
    (entries) => {
      const kept = new Set(entries.map((entry) => entry.id))
      for (const id of [...opened]) {
        if (kept.has(id)) continue
        opened.delete(id)
        manager.close(windowIdOf(id))
      }
      for (const entry of entries) {
        const windowId = windowIdOf(entry.id)
        if (opened.has(entry.id)) {
          manager.retitle(windowId, { title: entry.title, icon: appIcons.pair })
          continue
        }
        opened.add(entry.id)
        const pairId = entry.id
        const component = defineComponent({
          name: "PairWindowBody",
          setup() {
            // The window host is outside the workspace; only the targets need
            // its registry, and the panels keep their own injections.
            provide(panelTargetsKey, registry)
            return () => {
              const pair = props.pairs.pairs.value.find((one) => one.id === pairId)
              const minimized = manager.context.windows.value
                .find((one) => one.id === windowId)?.minimized ?? false
              return pair === undefined ? null : h(PairWindow, { pair, windowId, minimized })
            }
          },
        })
        manager.open({
          id: windowId,
          look: { title: entry.title, icon: appIcons.pair },
          component,
          actions: [{
            icon: appIcons.swapSides,
            tooltip: "Swap sides",
            testid: "pair-swap",
            run: () => { props.pairs.swap(pairId) },
          }],
          size: { width: 1120, height: 720 },
          minSize: { width: 640, height: 360 },
          autoFit: false,
          // Closing is taking the pair apart: both catalogs go home.
          beforeClose: () => {
            opened.delete(pairId)
            props.pairs.unpair(pairId)
            return true
          },
        })
      }
    },
    { immediate: true }
  )

  // Asking for a catalog that is in a pair brings the pair forward.
  if (workspace !== undefined) {
    watch(workspace.focusedDetached, (panelId) => {
      const pair = props.pairs.pairs.value.find(
        (one) => one.left.panelId === panelId || one.right.panelId === panelId
      )
      if (pair !== undefined) manager.context.focus(windowIdOf(pair.id))
    })
  }

  onBeforeUnmount(() => {
    for (const id of opened) manager.close(windowIdOf(id))
    opened.clear()
  })
}
</script>

<!-- eslint-disable vue/valid-template-root --
     Draws nothing itself: it opens and closes windows, which draw themselves
     elsewhere, as WorkspaceFloatingWindows does. -->
<template>
  <!-- Windows own the targets; the workspace owns the live panels. -->
</template>
