<script setup lang="ts">
import { computed, provide, ref } from "vue"

import { workspaceKey } from "./context"
import type { WorkspaceContext } from "./context"
import { createPanelTargets, panelTargetsKey } from "./panelTargets"
import WorkspacePanel from "./WorkspacePanel.vue"

const props = defineProps<{ context: WorkspaceContext }>()
const registry = createPanelTargets()
const parking = ref<HTMLElement | null>(null)
provide(workspaceKey, props.context)
provide(panelTargetsKey, registry)

const destinations = computed(() => new Map(
  [...registry.targets.value.values()].map((target) => [target.panelId, target.element])
))
</script>

<template>
  <slot />
  <div
    ref="parking"
    hidden
  />
  <template v-if="parking !== null">
    <WorkspacePanel
      v-for="panelId in context.panelIds.value"
      :key="context.keyOf(panelId)"
      :context="context"
      :panel-id="panelId"
      :target="destinations.get(panelId) ?? null"
      :parking="parking"
    />
  </template>
</template>
