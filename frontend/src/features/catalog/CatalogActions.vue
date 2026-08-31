<script setup lang="ts">
import { computed, ref } from "vue"

import ActionDialog from "@/features/catalog/ActionDialog.vue"
import { toMenu } from "@/features/catalog/actions"
import type { ActionOutcome, MenuCommand } from "@/features/catalog/actions"
import { useDownloadAction, useNodeActions } from "@/features/catalog/api"
import type { CatalogNode } from "@/features/catalog/nodes"
import { messageOf } from "@/shared/api/errors"
import { saveNativeDownload } from "@/shared/download"
import { AppIconButton, AppMenu, useToast } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

/**
 * What can be done, in one menu whose shape stays stable.
 *
 * The server decides which actions are live, and the client disables the rest:
 * what changes a node waits for a ticked row or an explicitly selected
 * grouping; what changes children belongs to the shown place; and what changes
 * the level itself ignores the grouping filter. Standing in a folder is not
 * choosing it, so nothing is renamed or removed because of where the user
 * happens to be. A source that has no actions at all shows no menu rather than
 * an empty one. See D56.
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
  /** The nodes that are ticked. */
  checkedIds: string[]
  checkedNodes: { label: string; kind: CatalogNode["kind"] }[]
  placeLabel: string
  checkedLabel: string
}>()

const emit = defineEmits<{ done: [outcome: ActionOutcome] }>()
const toast = useToast()
const downloadAction = useDownloadAction()

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

const items = computed<MenuItem[]>(() =>
  commands.value.map((command) => ({
    name: command.name,
    label: command.label,
    danger: command.destructive,
    disable: !command.enabled,
  }))
)

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
  const command = commands.value.find((one) => one.name === name) ?? null
  // A disabled item raises no click in Quasar; this is the second guard, so
  // that nothing opens a form for what the server would refuse anyway.
  if (command === null || !command.enabled) {
    active.value = null
    return
  }
  if (!command.downloads) {
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
  <span v-if="commands.length">
    <AppIconButton
      icon="more_vert"
      tooltip="Actions"
      data-testid="catalog-actions"
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
      @update:command="active = null"
      @done="emit('done', $event)"
    />
  </span>
</template>
