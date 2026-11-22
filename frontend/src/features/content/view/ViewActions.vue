<script setup lang="ts">
import { computed, ref } from "vue"

import ActionDialog from "@/features/catalog/ActionDialog.vue"
import { toCommands } from "@/features/catalog/actions"
import type { ActionCommand, ActionOutcome } from "@/features/catalog/actions"
import { useNodeActions, usePrepareConnectorAction } from "@/features/catalog/api"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { AppIconButton, AppToolbarRule, useToast } from "@/shared/ui"

/**
 * What the source offers to do to the node a view shows, by icon (D424).
 *
 * The same actions the catalog menu holds, asked the same way and opened in
 * the same window; which of them belong here is the source's `in_view`, not a
 * name this side knows. The catalog keeps them for a ticked set.
 */
const props = defineProps<{
  connectorId: string
  nodeId: string
  nodeLabel: string
}>()

const emit = defineEmits<{ done: [outcome: ActionOutcome] }>()

const workspace = useWorkspaceActions()
const toast = useToast()
const prepareConnector = usePrepareConnectorAction()
const actions = useNodeActions(
  computed(() => props.connectorId),
  computed(() => [props.nodeId])
)
const commands = computed<ActionCommand[]>(() =>
  toCommands(
    (actions.data.value ?? []).filter(
      (action) => action.in_view === true && action.applicable && action.acts_on === "node" && action.icon
    )
  )
)
const open = ref<ActionCommand | null>(null)

async function pick(command: ActionCommand) {
  if (command.preparesConnector) {
    if (prepareConnector.isPending.value) return
    try {
      const draft = await prepareConnector.mutateAsync({
        connectorId: props.connectorId,
        name: command.name,
        nodeId: props.nodeId,
      })
      workspace.createConnector(draft)
    } catch (cause) {
      toast.error(messageOf(cause, t("catalog.catalog_actions.connector_failed")))
    }
    return
  }
  open.value = command
}
</script>

<template>
  <template v-if="commands.length > 0">
    <AppIconButton
      v-for="command in commands"
      :key="command.name"
      :icon="command.icon ?? ''"
      :tooltip="command.label"
      :variant="command.destructive ? 'danger-quiet' : 'quiet'"
      :loading="command.preparesConnector && prepareConnector.isPending.value"
      :data-testid="`view-action-${command.name}`"
      @click="pick(command)"
    />
    <AppToolbarRule />
  </template>
  <ActionDialog
    v-if="open"
    :command="open"
    :connector-id="connectorId"
    :node-ids="[nodeId]"
    :node-label="nodeLabel"
    :target-node="null"
    @update:command="open = null"
    @done="emit('done', $event)"
  />
</template>
