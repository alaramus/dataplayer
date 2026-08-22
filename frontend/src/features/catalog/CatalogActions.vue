<script setup lang="ts">
import { computed, ref } from "vue"

import ActionDialog from "@/features/catalog/ActionDialog.vue"
import { toCommands } from "@/features/catalog/actions"
import type { ActionCommand } from "@/features/catalog/actions"
import { useNodeActions } from "@/features/catalog/api"
import { AppIconButton, AppMenu } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

/**
 * What can be done, in one menu.
 *
 * The target is what is ticked, and the current node when nothing is — that is
 * what makes "New folder" mean the folder being looked at. Which actions are
 * offered comes from the server for exactly that set of nodes, so the menu
 * cannot offer what the server would refuse. See the spec, S6.
 */
const props = defineProps<{
  connectorId: string
  /** The nodes to act on. `[null]` is the root of the connector. */
  nodeIds: (string | null)[]
  targetLabel: string
}>()

const emit = defineEmits<{ done: [reloadNodeIds: (string | null)[]] }>()

const connectorId = computed(() => props.connectorId)

// The route takes null for the root and a non-empty list otherwise; a list
// holding only null is the same question as no list at all.
const queryIds = computed<string[] | null>(() => {
  const named = props.nodeIds.filter((id): id is string => id !== null)
  return named.length === 0 ? null : named
})

const actions = useNodeActions(connectorId, queryIds)

const commands = computed(() => toCommands(actions.data.value ?? []))

const items = computed<MenuItem[]>(() =>
  commands.value.map((command) => ({
    name: command.name,
    label: command.label,
    danger: command.destructive,
  }))
)

const active = ref<ActionCommand | null>(null)

function pick(name: string) {
  active.value = commands.value.find((command) => command.name === name) ?? null
}
</script>

<template>
  <span>
    <AppIconButton
      icon="more_vert"
      tooltip="Actions"
      :disable="items.length === 0"
      data-testid="catalog-actions"
    />
    <AppMenu
      v-if="items.length"
      :items="items"
      @select="pick"
    />

    <ActionDialog
      v-model:command="active"
      :connector-id="connectorId"
      :node-ids="nodeIds"
      :node-label="targetLabel"
      @done="emit('done', $event)"
    />
  </span>
</template>
