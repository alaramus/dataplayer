<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { defineComponent, h } from "vue"
import type { Component } from "vue"
import { z } from "zod"

import {
  makeLeaf,
  makeSplit,
  useWorkspace,
  WorkspaceRoot,
  WorkspaceTaskbar,
} from "@/shared/workspace"
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

/** What a column of this demo keeps on screen at forty pixels. */
const Rail = defineComponent({
  setup: () => () =>
    h("div", { style: "padding: 8px 0; text-align: center; font-size: 11px;" }, "A"),
})

/** And what a column with nothing in it says instead. */
const Hint = defineComponent({
  setup: () => () =>
    h(
      "div",
      { style: "padding: 12px; font-size: 13px; color: var(--dp-text-muted);" },
      "Nothing is open here yet"
    ),
})

const workspace = useWorkspace<DemoPanel>({
  storageKey: "dataplayer-workspace-demo",
  panelSchema,
  defaults: () => ({
    tree: makeSplit(
      "root",
      "row",
      [
        // A role each, because a drop is judged by one: a section that names
        // none takes nothing, and the demo is here to exercise the engine as
        // the application uses it. See P1.
        makeLeaf("left", ["alpha"], { accepts: "alpha" }),
        makeLeaf("main", ["beta", "gamma"], { accepts: "beta" }),
        // A column that exists before anything is opened in it, so the three
        // states of a head are all on this page: narrow it, put it aside, and
        // neither.
        makeLeaf("notes", [], { accepts: "note", pinned: true }),
      ],
      [24, 50, 26]
    ),
    panels: [
      { id: "alpha", kind: "alpha", title: "Alpha" },
      { id: "beta", kind: "beta", title: "Beta" },
      { id: "gamma", kind: "beta", title: "Gamma" },
    ],
  }),
  kindOf: (panel) => panel.kind,
  look: (panel) => ({ title: panel.title, icon: appIcons.widgets }),
  component: (panel) => Placeholder(panel.id, panel.title),
  // One column has something worth forty pixels and narrows to them; the other
  // has not, is named, and goes to the bar whole.
  collapsed: (panel) => (panel.kind === "alpha" ? Rail : null),
  empty: (accepts) => (accepts === "note" ? Hint : null),
  sectionLook: (accepts) =>
    accepts === "beta" ? { title: "Data", icon: appIcons.tableChart } : null,
})

let opened = 0

function openOne() {
  opened += 1
  const id = `demo-${String(opened)}`
  workspace.open({ id, kind: "beta", title: `Demo ${String(opened)}` })
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
      <!-- Where the application puts it is the bar at the foot of the screen;
           here it stands beside the buttons, which is the same bar's job. -->
      <WorkspaceTaskbar :context="workspace.context" />
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
  gap: var(--dp-space-2);
  padding: var(--dp-space-2);
}
/* The ground the application stands the workspace on, so this page shows the
   cards against what they are actually drawn against. */
.demo__area {
  flex: 1;
  min-height: 0;
  border-top: 1px solid var(--dp-border);
  padding: var(--dp-workspace-inset);
  background: var(--dp-chrome);
}
</style>
