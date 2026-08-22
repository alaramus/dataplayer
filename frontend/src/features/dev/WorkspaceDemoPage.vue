<script setup lang="ts">
import { defineComponent, h } from "vue"
import type { Component } from "vue"
import { z } from "zod"

import { makeLeaf, makeSplit, useWorkspace, WorkspaceRoot } from "@/shared/workspace"
import { AppButton } from "@/shared/ui"

/**
 * The engine on its own, with panels that show nothing but their own name.
 * A development route, like /ui-kit: it renders the real components, so it
 * breaks when one of them does.
 */

const panelSchema = z.object({ id: z.string(), kind: z.string(), title: z.string() })
type DemoPanel = z.infer<typeof panelSchema>

/**
 * One component per panel, kept.
 *
 * The engine asks for the component of the active panel on every render and
 * keeps a tab that is not showing alive, so the answer has to be the same
 * component every time — see `WorkspaceOptions.component`.
 */
const placeholders = new Map<string, Component>()

const Placeholder = (id: string, title: string) => {
  const kept = placeholders.get(id)
  if (kept !== undefined) return kept
  const made = defineComponent({
    setup: () => () => h("div", { style: "padding: 12px; font-size: 13px;" }, title),
  })
  placeholders.set(id, made)
  return made
}

const workspace = useWorkspace<DemoPanel>({
  storageKey: "dataplayer-workspace-demo",
  panelSchema,
  defaults: () => ({
    tree: makeSplit(
      "root",
      "row",
      [makeLeaf("left", ["alpha"]), makeLeaf("main", ["beta", "gamma"])],
      [30, 70]
    ),
    panels: [
      { id: "alpha", kind: "alpha", title: "Alpha" },
      { id: "beta", kind: "beta", title: "Beta" },
      { id: "gamma", kind: "beta", title: "Gamma" },
    ],
  }),
  kindOf: (panel) => panel.kind,
  look: (panel) => ({ title: panel.title, icon: "widgets" }),
  component: (panel) => Placeholder(panel.id, panel.title),
})

let opened = 0

function openOne() {
  opened += 1
  const id = `demo-${String(opened)}`
  workspace.open({ id, kind: "demo", title: `Demo ${String(opened)}` })
}
</script>

<template>
  <div class="demo">
    <div class="demo__bar">
      <AppButton
        size="sm"
        label="Open a panel"
        data-testid="open-demo-panel"
        @click="openOne"
      />
      <AppButton
        size="sm"
        variant="quiet"
        label="Reset layout"
        data-testid="reset-workspace"
        @click="workspace.reset()"
      />
    </div>
    <div class="demo__area">
      <WorkspaceRoot :context="workspace.context" />
    </div>
  </div>
</template>

<style scoped>
.demo {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.demo__bar {
  display: flex;
  gap: 8px;
  padding: 8px;
}
.demo__area {
  flex: 1;
  min-height: 0;
  border-top: 1px solid rgba(0, 0, 0, 0.12);
}
</style>
