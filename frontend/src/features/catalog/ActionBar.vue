<script setup lang="ts">
import { computed, ref } from "vue"

import ActionDialog from "@/features/catalog/ActionDialog.vue"
import { toCommands } from "@/features/catalog/actions"
import type { ActionCommand } from "@/features/catalog/actions"
import { useNodeActions } from "@/features/catalog/api"
import { AppButton } from "@/shared/ui"

const props = defineProps<{
  connectorId: string
  nodeId: string | null
  nodeLabel: string
}>()

const emit = defineEmits<{ done: [reloadNodeId: string | null] }>()

const connectorId = computed(() => props.connectorId)
const nodeId = computed(() => props.nodeId)

const actions = useNodeActions(connectorId, nodeId)

// Buttons come from the answer of the server, in the order it sent them. There
// is nothing here that knows what a file source or a database is.
const commands = computed(() => toCommands(actions.data.value ?? []))

const active = ref<ActionCommand | null>(null)
</script>

<template>
  <div
    v-if="commands.length"
    class="row items-center q-gutter-sm q-mb-sm"
    data-testid="action-bar"
  >
    <span class="text-caption text-grey">{{ nodeLabel }}</span>
    <AppButton
      v-for="command in commands"
      :key="command.name"
      size="sm"
      :variant="command.destructive ? 'danger-quiet' : 'secondary'"
      :label="command.label"
      :data-testid="`action-${command.name}`"
      @click="active = command"
    />

    <ActionDialog
      v-model:command="active"
      :connector-id="connectorId"
      :node-id="nodeId"
      :node-label="nodeLabel"
      @done="emit('done', $event)"
    />
  </div>
</template>
