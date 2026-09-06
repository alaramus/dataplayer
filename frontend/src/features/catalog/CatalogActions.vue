<script setup lang="ts">
import { computed, ref } from "vue"

import type { ConnectorDraft } from "@/client"
import ActionDialog from "@/features/catalog/ActionDialog.vue"
import {
  clientCommandOf,
  clientMenu,
  needsClipboard,
  toMenu,
} from "@/features/catalog/actions"
import { clipboardWording, heldFor, holdNodes } from "@/features/catalog/clipboard"
import type {
  ActionOutcome,
  ClientCommand,
  Grouping,
  MenuCommand,
} from "@/features/catalog/actions"
import { useDownloadAction, useNodeActions, usePrepareConnectorAction } from "@/features/catalog/api"
import type { CatalogNode } from "@/features/catalog/nodes"
import { messageOf } from "@/shared/api/errors"
import { saveNativeDownload } from "@/shared/download"
import { AppIconButton, AppMenu, useToast } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

/**
 * What can be done, in one menu whose shape stays stable (D56). The server
 * decides which lines are live; nothing is renamed or removed because of where
 * the user happens to be, since standing in a folder is not choosing it.
 *
 * The client's own verbs are lines of the same menu, so a source with neither
 * actions nor described nodes shows nothing rather than an empty menu.
 */
const props = defineProps<{
  connectorId: string
  /** The level itself, before selected groupings contribute their children. */
  levelId: string | null
  levelLabel: string
  /**
   * Where something new would be made: the groupings whose contents are on
   * screen, or the level itself when the source offers none. `null` is the
   * root of the connector.
   */
  places: (string | null)[]
  /** Groupings explicitly selected in the level control. */
  selectedGroups: { id: string; label: string; kind: CatalogNode["kind"] }[]
  /** Every grouping the level offers, for a form whose field names one. */
  groupings: Grouping[]
  /** The nodes that are ticked. */
  checkedIds: string[]
  checkedNodes: { label: string; kind: CatalogNode["kind"] }[]
  placeLabel: string
  checkedLabel: string
  /** Whether the source describes the nodes of this level (D75). */
  describesNodes: boolean
  /** The one ticked node it will describe, or nothing. */
  describedNode: { id: string; label: string } | null
  /** Whether anything on this level has a structure to draw as a diagram (D97). */
  drawsNodes: boolean
  /** Whether what would be drawn — the ticks, or the list — is a set a diagram can hold. */
  drawableNodes: boolean
}>()

const emit = defineEmits<{
  done: [outcome: ActionOutcome]
  details: []
  relationships: []
  connector: [draft: ConnectorDraft]
}>()
const toast = useToast()
const downloadAction = useDownloadAction()
const prepareConnector = usePrepareConnectorAction()

const connectorId = computed(() => props.connectorId)

const levelIds = computed<string[] | null>(() =>
  props.levelId === null || props.levelId === "" ? null : [props.levelId]
)

// The route takes null for the root and a non-empty list otherwise.
const placeIds = computed<string[] | null>(() => {
  const named = props.places.filter((id): id is string => id !== null && id !== "")
  return named.length === 0 ? null : named
})
const nodeTargetIds = computed(() =>
  props.checkedIds.length > 0
    ? [...props.checkedIds]
    : props.selectedGroups.map((group) => group.id)
)
const pickedIds = computed<string[] | null>(() =>
  nodeTargetIds.value.length === 0 ? null : [...nodeTargetIds.value]
)
const nodeTargetNodes = computed(() =>
  props.checkedIds.length > 0 ? props.checkedNodes : props.selectedGroups
)
const anyChecked = computed(() => nodeTargetIds.value.length > 0)

// Three questions, because a menu line is about one of three subjects: the
// level itself, the places whose contents are shown, or an explicit node
// selection. The vocabulary is the same in every answer, so the level answer
// is enough to draw the stable menu before anything is selected.
const level = useNodeActions(connectorId, levelIds)
const here = useNodeActions(connectorId, placeIds)
const picked = useNodeActions(connectorId, pickedIds, anyChecked)

const commands = computed(() =>
  toMenu(
    level.data.value ?? [],
    here.data.value ?? [],
    picked.data.value ?? [],
    props.levelId,
    props.places,
    nodeTargetIds.value
  )
)

/**
 * What the catalog is holding for this connection, if anything.
 *
 * Copy and Cut change nothing on the server: they remember a selection here,
 * and the source's own command is what puts it somewhere (D74).
 */
const held = computed(() => heldFor(props.connectorId))
const canHold = computed(() =>
  commands.value.some((command) => needsClipboard(command))
)

/**
 * One menu, two vocabularies: what the client can do, then what the source can.
 *
 * The client's three come first because they are the same three wherever one
 * stands, while the source's own lines vary with the level — and because Copy
 * and Cut read as the pair Paste completes when they sit above it.
 */
const items = computed<MenuItem[]>(() => [
  ...clientMenu({
    describes: props.describesNodes,
    describable: props.describedNode !== null,
    diagrams: props.drawsNodes,
    diagrammable: props.drawableNodes,
    holds: canHold.value,
    ticked: props.checkedIds.length,
  }),
  ...commands.value.map((command) => ({
    name: command.name,
    label: needsClipboard(command) && held.value !== null
      ? `${command.label} — ${clipboardWording(held.value)}`
      : command.label,
    danger: command.destructive,
    disable:
      !command.enabled || (needsClipboard(command) && held.value === null),
  })),
])

/** A verb of the client's: nothing is sent, and nothing waits for an answer. */
function run(command: ClientCommand) {
  if (command === "details") {
    if (props.describedNode !== null) emit("details")
    return
  }
  // A diagram is the one client verb that works without ticks: what is listed
  // is the scope when nothing is picked out of it.
  if (command === "relationships") {
    if (props.drawableNodes) emit("relationships")
    return
  }
  if (props.checkedIds.length === 0) return
  holdNodes(props.connectorId, [...props.checkedIds], command === "copy" ? "copy" : "move")
}

const active = ref<MenuCommand | null>(null)

const targetLabel = computed(() => {
  if (active.value?.actsOn === "level") return props.levelLabel
  if (active.value?.actsOn === "children") return props.placeLabel
  if (props.checkedIds.length > 0) return props.checkedLabel
  return props.selectedGroups.map((group) => group.label).join(", ")
})
const targetNode = computed(() =>
  active.value?.actsOn === "node" && nodeTargetNodes.value.length === 1
    ? nodeTargetNodes.value[0] ?? null
    : null
)

async function pick(name: string) {
  if (prepareConnector.isPending.value) return
  const client = clientCommandOf(name)
  if (client !== null) {
    run(client)
    return
  }
  const command = commands.value.find((one) => one.name === name) ?? null
  // A disabled item raises no click in Quasar; this is the second guard, so
  // that nothing opens a form for what the server would refuse anyway.
  if (command === null || !command.enabled) {
    active.value = null
    return
  }
  if (needsClipboard(command) && held.value === null) {
    active.value = null
    return
  }
  if (command.preparesConnector) {
    const nodeId = command.targets[0]
    if (command.targets.length !== 1 || nodeId === null || nodeId === undefined) return
    try {
      const draft = await prepareConnector.mutateAsync({
        connectorId: props.connectorId,
        name: command.name,
        nodeId,
      })
      emit("connector", draft)
    } catch (cause) {
      toast.error(messageOf(cause, "The connector form could not be prepared"))
    }
    return
  }
  // A download runs straight from the menu only when it has nothing to ask
  // and nothing to show. One with a form goes through the form, and one with
  // a screen of its own goes through that (D73).
  if (
    !command.downloads ||
    command.fields.length > 0 ||
    command.workflow !== undefined
  ) {
    active.value = command
    return
  }

  // A download action receives the selection once. Whether that becomes one
  // original object, an archive or another source-native result belongs to
  // the source; this menu only follows the returned native-browser route.
  try {
    const ready = await downloadAction.mutateAsync({
      connectorId: props.connectorId,
      name: command.name,
      nodeIds: command.targets.filter((id): id is string => id !== null),
    })
    saveNativeDownload(ready.download_url)
  } catch (cause) {
    toast.error(messageOf(cause, "The download could not be prepared"))
  }
}
</script>

<template>
  <!-- Drawn while there is anything to offer, which is now either the source's
       actions or the client's own verbs: a source with no actions at all still
       describes its nodes. -->
  <span v-if="items.length">
    <AppIconButton
      icon="more_vert"
      tooltip="Actions"
      data-testid="catalog-actions"
      :loading="prepareConnector.isPending.value"
    />
    <AppMenu
      :items="items"
      @select="pick"
    />

    <!-- Not v-model: the dialog only ever gives the command back closed, and
         binding it would narrow the menu command to the plainer one it takes. -->
    <ActionDialog
      :command="active"
      :connector-id="connectorId"
      :node-ids="active?.targets ?? []"
      :node-label="targetLabel"
      :target-node="targetNode"
      :groupings="groupings"
      @update:command="active = null"
      @done="emit('done', $event)"
    />
  </span>
</template>
