<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query"
import { computed, ref } from "vue"

import { ConnectorsService } from "@/client"
import type { ConnectorDraft } from "@/client"
import { appIcons } from "@/shared/ui/icons"
import ActionDialog from "@/features/catalog/ActionDialog.vue"
import CrossPaste from "@/features/catalog/CrossPaste.vue"
import DeclareTableWindow from "@/features/catalog/DeclareTableWindow.vue"
import {
  clientCommandOf,
  clientMenu,
  needsClipboard,
  toMenu,
} from "@/features/catalog/actions"
import {
  clipboard,
  heldFor,
  holdNodes,
} from "@/features/catalog/clipboard"
import { holdLines, pasteHint, pasteLines, usableOffers } from "@/features/catalog/pasteOffers"
import type { CrossPasteIntent } from "@/features/catalog/pasteOffers"
import type {
  ActionOutcome,
  ClientCommand,
  Grouping,
  MenuCommand,
} from "@/features/catalog/actions"
import {
  useDownloadAction,
  useNodeActions,
  usePrepareConnectorAction,
} from "@/features/catalog/api"
import type { CatalogNode } from "@/features/catalog/nodes"
import { useAdapterTypes } from "@/features/connectors/api"
import { useBackupSupport } from "@/features/services/backups"
import { messageOf } from "@/shared/api/errors"
import { saveNativeDownload } from "@/shared/download"
import { AppIconButton, AppMenu, AppToolbarRule, useToast } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

/**
 * What can be done, in one menu whose shape stays stable (D56). The server
 * decides which lines are live; nothing is renamed or removed because of where
 * the user happens to be, since standing in a folder is not choosing it.
 *
 * The client's own verbs are lines of the same menu, so a source with neither
 * actions nor described nodes shows nothing rather than an empty menu. It is
 * the last of the catalog's commands and draws the line before it, which then
 * goes with it.
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
  /** Whether this source draws the structure of what it holds as a diagram (D97). */
  drawsNodes: boolean
  /** Whether what would be drawn — the ticks, or the list — is a set a diagram can hold. */
  drawableNodes: boolean
  /** What kind of source this is, for the one command about the connection. */
  adapterType: string
}>()

const emit = defineEmits<{
  done: [outcome: ActionOutcome]
  /** Carried out on the ticked nodes with no outcome to report: they are let go. */
  untick: []
  sourceChanged: [connectorId: string]
  details: []
  relationships: []
  backups: []
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
const groupIds = computed(() => props.selectedGroups.map((group) => group.id))
const hasGroups = computed(() => groupIds.value.length > 0)
const destinationIds = computed(() => [
  ...props.places.filter((id): id is string =>
    id !== null && props.groupings.some((group) => group.id === id)
  ),
  ...props.groupings.map((group) => group.id).filter((id) => !props.places.includes(id)),
])
const hasDestinations = computed(() => destinationIds.value.length > 0)

// Equal target lists share a query; row ticks never replace the grouping subject (D118).
const level = useNodeActions(connectorId, levelIds)
const here = useNodeActions(connectorId, placeIds)
const picked = useNodeActions(connectorId, pickedIds, anyChecked)
const groups = useNodeActions(connectorId, groupIds, hasGroups)
const destinations = useNodeActions(connectorId, destinationIds, hasDestinations)

const commands = computed(() =>
  toMenu({
    level: { actions: level.data.value ?? [], targets: [props.levelId] },
    children: { actions: here.data.value ?? [], targets: props.places },
    node: { actions: picked.data.value ?? [], targets: nodeTargetIds.value },
    group: { actions: groups.data.value ?? [], targets: groupIds.value },
    destination: { actions: destinations.data.value ?? [], targets: destinationIds.value },
  })
)

/**
 * What the catalog is holding for this connection, if anything.
 *
 * Copy and Cut change nothing on the server: they remember a selection here,
 * and the source's own command is what puts it somewhere (D74).
 */
const held = computed(() => heldFor(props.connectorId))
/** Whether the source has a Paste of its own for what it lists (D74). */
const canHold = computed(() =>
  commands.value.some((command) => needsClipboard(command))
)
/**
 * A selection the application pastes: from another connection (D161, D163),
 * or from this one when the source has no Paste of its own — which is how a
 * table gets a copy beside itself (D182). Not before the source's own actions
 * have answered, while it is not yet known which of the two it is.
 */
const crossHeld = computed(() => {
  const clipped = clipboard.value
  if (clipped === null) return null
  if (clipped.connectorId !== props.connectorId) return clipped
  return level.data.value !== undefined && !canHold.value ? clipped : null
})
const crossPlace = computed(() =>
  props.places.length === 1 ? props.places[0] ?? null : null
)
/** The one node ticked here, which rows can be pasted into (D166). */
const crossTarget = computed(() =>
  props.checkedIds.length === 1 ? props.checkedIds[0] ?? null : null
)
const crossOffers = useQuery({
  queryKey: computed(() => [
    "paste-offers", props.connectorId, crossPlace.value, crossTarget.value, crossHeld.value,
  ]),
  // Asked wherever the catalog stands: a kind that needs one place says so,
  // and a copy of tables chooses its schema in its window (D182).
  enabled: computed(() => crossHeld.value !== null),
  retry: false,
  queryFn: async () => {
    const source = crossHeld.value
    if (source === null) throw new Error("Copy something first")
    return (await ConnectorsService.pasteOffers({
      path: { connector_id: props.connectorId },
      body: {
        source_connector_id: source.connectorId,
        source_node_ids: source.nodeIds,
        destination_node_id: crossPlace.value,
        target_node_id: crossTarget.value,
        mode: source.mode,
      },
    })).data.offers
  },
})
const crossLines = computed(() => pasteLines(crossOffers.data.value ?? []))
const crossUsable = computed(() => usableOffers(crossLines.value.paste))
// Asked only of a source without a Paste of its own, and only once its own
// actions have answered: until then it is not known which one this is.
const holdOffer = useQuery({
  queryKey: computed(() => ["clipboard-offer", props.connectorId, [...props.checkedIds]]),
  enabled: computed(() => level.data.value !== undefined && !canHold.value),
  retry: false,
  queryFn: async () => (await ConnectorsService.clipboardOffer({
    path: { connector_id: props.connectorId },
    body: { node_ids: [...props.checkedIds] },
  })).data,
})
const holds = computed(() =>
  holdLines(canHold.value, props.checkedIds.length, holdOffer.data.value)
)

/**
 * The one line about the connection rather than about a node in it.
 *
 * It used to stand in the footer beside the library of queries, where it was
 * the only command in that bar acting on the open connection while the rest
 * of what a connection can do already lived in this menu.
 */
const backups = useBackupSupport(() => props.adapterType)

/**
 * The node "Describe as table" is about: the one ticked, or the level itself —
 * a folder picked in a tree — when nothing is (D170).
 */
const tableSubject = computed<string | null>(() => {
  if (props.checkedIds.length === 1) return props.checkedIds[0] ?? null
  return props.checkedIds.length === 0 ? props.levelId : null
})
const tableSubjectLabel = computed(() =>
  props.checkedIds.length === 1 ? props.checkedLabel : props.levelLabel
)
const adapterTypes = useAdapterTypes()
/** Only a source that says so can have a table declared over it. */
const declaresTables = computed(() =>
  (adapterTypes.data.value ?? []).some(
    (type) =>
      type.name === props.adapterType &&
      type.capabilities.some((capability) => capability.code === "declared_tables")
  )
)
const tableOffer = useQuery({
  queryKey: computed(() => ["table-offer", props.connectorId, tableSubject.value]),
  enabled: declaresTables,
  retry: false,
  queryFn: async () => (await ConnectorsService.tableOffer({
    path: { connector_id: props.connectorId },
    body: { node_id: tableSubject.value },
  })).data,
})
const tableLine = computed(() => {
  if (!declaresTables.value) return undefined
  const answer = tableOffer.data.value
  if (answer === undefined) {
    return { enabled: false, reason: tableOffer.isError.value
      ? "Could not check this selection"
      : "Checking this selection" }
  }
  return answer.available
    ? { enabled: true }
    : { enabled: false, ...(answer.reason ? { reason: answer.reason } : {}) }
})
/** The declaration window, with the node it was opened on. */
const declaring = ref<{ nodeId: string; label: string } | null>(null)

/**
 * One menu, two vocabularies: what the client can do, then what the source can.
 *
 * The client's come first because they are the same wherever one stands, while
 * the source's own lines vary with the level — and because Copy and Cut read
 * as the pair Paste completes when they sit above it.
 */
const items = computed<MenuItem[]>(() => [
  ...clientMenu({
    describes: props.describesNodes,
    describable: props.describedNode !== null,
    diagrams: props.drawsNodes,
    diagrammable: props.drawableNodes,
    ...holds.value,
    ...(tableLine.value ? { table: tableLine.value } : {}),
    ...(backups.value.offered
      ? {
          backups: {
            enabled: backups.value.enabled,
            ...(backups.value.reason === undefined ? {} : { reason: backups.value.reason }),
          },
        }
      : {}),
  }),
  ...(crossHeld.value === null ? [] : [{
    name: "client:cross-paste",
    label: "Paste",
    disable: crossUsable.value.length === 0,
    hint: pasteHint({
      checking: crossOffers.isPending.value,
      failed: crossOffers.isError.value,
      offers: crossOffers.data.value === undefined ? undefined : crossLines.value.paste,
    }),
  }]),
  ...(crossHeld.value === null || crossLines.value.into === null ? [] : [{
    name: "client:cross-paste-into",
    label: crossLines.value.into.title,
    disable: !crossLines.value.into.available,
    hint: crossLines.value.into.available ? undefined : crossLines.value.into.reason ?? undefined,
  }]),
  ...commands.value.filter((command) => crossHeld.value === null || !needsClipboard(command)).map((command) => {
    // An empty clipboard is the client's own reason and outranks the source's,
    // because it is the one the reader can act on immediately.
    const empty = needsClipboard(command) && held.value === null
    return {
      name: command.name,
      label: command.label,
      danger: command.destructive,
      disable: !command.enabled || empty,
      hint: empty
        ? "Copy or cut something first"
        : command.enabled ? undefined : command.reason ?? undefined,
    }
  }),
])

/** A verb of the client's: nothing is sent, and nothing waits for an answer. */
function run(command: ClientCommand) {
  if (command === "details") {
    if (props.describedNode !== null) emit("details")
    return
  }
  // A diagram works without ticks: what is listed is the scope when nothing is
  // picked out of it.
  if (command === "relationships") {
    if (props.drawableNodes) emit("relationships")
    return
  }
  // And copying the connection out is about no node in it at all.
  if (command === "backups") {
    if (backups.value.enabled) emit("backups")
    return
  }
  if (command === "describe-table") {
    const nodeId = tableSubject.value
    if (nodeId !== null && tableLine.value?.enabled === true) {
      declaring.value = { nodeId, label: tableSubjectLabel.value }
    }
    return
  }
  if (props.checkedIds.length === 0) return
  holdNodes(
    props.connectorId,
    [...props.checkedIds],
    command === "copy" ? "copy" : "move",
    props.checkedLabel
  )
  // Said aloud, because the ticks go: they were the only sign that anything
  // had been taken, and Paste aims at a ticked node.
  const what = props.checkedIds.length === 1 ? `“${props.checkedLabel}”` : props.checkedLabel
  toast.success(
    `${command === "copy" ? "Copied" : "Cut"} ${what} — paste it from the actions menu where it should go`
  )
  emit("untick")
}

/**
 * The forms this menu has opened, one window each.
 *
 * A list rather than one command at a time: how many windows are worth having
 * open is the user's decision, and a second action used to replace the first
 * one's window with its own contents. Each entry carries the target it was
 * opened on, because the ticks move on while the form stays.
 */
interface OpenAction {
  key: string
  /** The action and what it was opened on, so one pair is one window. */
  signature: string
  command: MenuCommand
  nodeLabel: string
  targetNode: { label: string; kind: CatalogNode["kind"] } | null
}

const opened = ref<OpenAction[]>([])
let openings = 0

/** The Paste from another connection under way, and its windows. */
const crossPasting = ref<CrossPasteIntent | null>(null)
let pastings = 0

function labelFor(command: MenuCommand) {
  if (command.actsOn === "level") return props.levelLabel
  if (command.actsOn === "children") return props.placeLabel
  if (command.actsOn === "group" || command.actsOn === "destination") {
    return props.groupings.filter((group) => command.targets.includes(group.id))
      .map((group) => group.label).join(", ")
  }
  if (props.checkedIds.length > 0) return props.checkedLabel
  return props.selectedGroups.map((group) => group.label).join(", ")
}

function nodeFor(command: MenuCommand) {
  const nodes = command.actsOn === "group" ? props.selectedGroups : nodeTargetNodes.value
  return (command.actsOn === "node" || command.actsOn === "group") && nodes.length === 1
    ? nodes[0] ?? null
    : null
}

/** One window per action and target: picking the same line twice is one form. */
function openForm(command: MenuCommand) {
  const signature = `${command.name}:${command.targets.join(",")}`
  if (opened.value.some((entry) => entry.signature === signature)) return
  openings += 1
  opened.value = [
    ...opened.value,
    {
      key: `a${openings}`,
      signature,
      command,
      nodeLabel: labelFor(command),
      targetNode: nodeFor(command),
    },
  ]
}

function closeForm(key: string) {
  opened.value = opened.value.filter((entry) => entry.key !== key)
}

async function pick(name: string) {
  if (prepareConnector.isPending.value) return
  if (name === "client:cross-paste" || name === "client:cross-paste-into") {
    const source = crossHeld.value
    const into = crossLines.value.into
    const offers = name === "client:cross-paste"
      ? crossUsable.value
      : into?.available === true ? [into] : []
    if (source === null || offers.length === 0 || crossPasting.value !== null) return
    pastings += 1
    crossPasting.value = {
      sourceConnectorId: source.connectorId,
      sourceNodeIds: [...source.nodeIds],
      sourceLabel: source.label ?? "The copied selection",
      mode: source.mode,
      destinationConnectorId: props.connectorId,
      destinationNodeId: crossPlace.value,
      destinationLabel: props.placeLabel,
      targetNodeId: crossTarget.value,
      targetLabel: props.checkedLabel,
      offers,
    }
    return
  }
  const client = clientCommandOf(name)
  if (client !== null) {
    run(client)
    return
  }
  const command = commands.value.find((one) => one.name === name) ?? null
  // A disabled item raises no click in Quasar; this is the second guard, so
  // that nothing opens a form for what the server would refuse anyway.
  if (command === null || !command.enabled) return
  if (needsClipboard(command) && held.value === null) return
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
    openForm(command)
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
    emit("untick")
  } catch (cause) {
    toast.error(messageOf(cause, "The download could not be prepared"))
  }
}
</script>

<template>
  <!-- Drawn while there is anything to offer, which is now either the source's
       actions or the client's own verbs: a source with no actions at all still
       describes its nodes. -->
  <span
    v-if="items.length"
    class="catalog-actions"
  >
    <AppToolbarRule />
    <!-- A menu opens from its parent: a span of its own, so the line beside
         the button is not a place to press. -->
    <span>
      <AppIconButton
        :icon="appIcons.moreVert"
        tooltip="Actions"
        data-testid="catalog-actions"
        :loading="prepareConnector.isPending.value"
      />
      <AppMenu
        :items="items"
        @select="pick"
      />
    </span>

    <!-- Not v-model: the dialog only ever gives the command back closed, and
         binding it would narrow the menu command to the plainer one it takes. -->
    <ActionDialog
      v-for="entry in opened"
      :key="entry.key"
      :command="entry.command"
      :connector-id="connectorId"
      :node-ids="entry.command.targets"
      :node-label="entry.nodeLabel"
      :target-node="entry.targetNode"
      :groupings="groupings"
      @update:command="closeForm(entry.key)"
      @done="emit('done', $event)"
    />
    <CrossPaste
      v-if="crossPasting"
      :key="pastings"
      :intent="crossPasting"
      @done="emit('done', $event)"
      @started="emit('untick')"
      @source-changed="emit('sourceChanged', $event)"
      @close="crossPasting = null"
    />
    <DeclareTableWindow
      v-if="declaring"
      :key="declaring.nodeId"
      :connector-id="connectorId"
      :node-id="declaring.nodeId"
      :node-label="declaring.label"
      @done="emit('done', $event)"
      @close="declaring = null"
    />
  </span>
</template>

<style scoped>
/* As tall as the row it ends, so its line is as long as the others. */
.catalog-actions {
  display: flex;
  align-items: center;
  align-self: stretch;
}
</style>
