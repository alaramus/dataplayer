<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { defineComponent, h, inject, onBeforeUnmount, provide, ref, watch } from "vue"
import type { Ref } from "vue"

import { windowsApiKey } from "@/shared/windows/useWindows"

import type { WorkspaceContext } from "./context"
import { panelTargetsKey } from "./panelTargets"
import WorkspaceFloatingPanel from "./WorkspaceFloatingPanel.vue"

const props = defineProps<{ context: WorkspaceContext }>()
/**
 * The engine's own state, which this component is handed rather than owns.
 *
 * Named once here because writing `props.context.focusedDetached.value` reads
 * as changing a prop and is linted as one, while what it changes is a ref
 * inside an object every part of the workspace shares — the same object
 * `WorkspaceLeaf` reaches by injection and writes to in the same way.
 */
const workspace = props.context
const windows = inject(windowsApiKey)
const targets = inject(panelTargetsKey)
const opened = new Map<string, { windowId: string; panelId: Ref<string> }>()

if (windows !== undefined && targets !== undefined) {
  const manager = windows
  const registry = targets
  watch(
    // A group's window is drawn by the feature that made the group.
    () => props.context.detached.value.filter((entry) => entry.group === undefined).map((entry) => ({
      ...entry, look: props.context.lookOf(entry.panelId),
    })),
    (entries) => {
      const kept = new Set(entries.map((entry) => entry.fallbackLeafId))
      for (const [key, record] of opened) {
        if (kept.has(key)) continue
        opened.delete(key)
        manager.close(record.windowId)
      }
      for (const entry of entries) {
        const existing = opened.get(entry.fallbackLeafId)
        if (existing !== undefined) {
          existing.panelId.value = entry.panelId
          manager.retitle(existing.windowId, entry.look)
          continue
        }
        const windowId = `workspace:${entry.fallbackLeafId}`
        const panelId = ref(entry.panelId)
        opened.set(entry.fallbackLeafId, { windowId, panelId })
        const component = defineComponent({
          name: "DetachedPanelTarget",
          setup() {
            // The window host is outside the workspace. Only its DOM target
            // needs this registry; the live panel keeps its page injections.
            provide(panelTargetsKey, registry)
            return () => h(WorkspaceFloatingPanel, {
              panelId: panelId.value, targetId: windowId,
              minimized: manager.context.windows.value.find((one) => one.id === windowId)?.minimized ?? false,
            })
          },
        })
        manager.open({
          id: windowId, look: entry.look, component,
          // The way back sits with the other things this frame can do to
          // itself, rather than inside the panel it holds (D112).
          actions: [{
            icon: appIcons.tab,
            tooltip: "Return to panel",
            testid: "dock-panel",
            run: () => { props.context.dock(panelId.value) },
          }],
          size: { width: 960, height: 640 }, minSize: { width: 360, height: 240 }, autoFit: false,
          beforeClose: async () => {
            await props.context.requestClose(panelId.value)
            // A panel may have changed id while its confirmation was open.
            // Keep the frame if that same detached slot still holds a panel.
            return !props.context.detached.value.some((one) => one.fallbackLeafId === entry.fallbackLeafId)
          },
          onFocus: () => { workspace.focusedDetached.value = panelId.value },
        })
      }
    },
    { immediate: true }
  )

  watch(props.context.focusedDetached, (panelId) => {
    const record = [...opened.values()].find((one) => one.panelId.value === panelId)
    if (record !== undefined) manager.context.focus(record.windowId)
  })
  watch(manager.context.frontId, (windowId) => {
    const record = [...opened.values()].find((one) => one.windowId === windowId)
    workspace.focusedDetached.value = record?.panelId.value ?? null
  })
  onBeforeUnmount(() => {
    for (const record of opened.values()) manager.close(record.windowId)
    opened.clear()
  })
}
</script>

<!-- eslint-disable vue/valid-template-root --
     This component draws nothing at all: it opens and closes windows, and the
     windows draw themselves elsewhere. A root element would be an empty box
     in the middle of the workspace, so the template is deliberately a comment
     and the rule that wants a child element is switched off for it. -->
<template>
  <!-- Windows own targets; WorkspacePanels owns the live panel instances. -->
</template>
