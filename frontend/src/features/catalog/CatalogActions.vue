<script setup lang="ts">
import { computed, ref } from "vue"

import ActionDialog from "@/features/catalog/ActionDialog.vue"
import { toMenu } from "@/features/catalog/actions"
import type { ActionOutcome, MenuCommand } from "@/features/catalog/actions"
import { useDownloadAction, useNodeActions } from "@/features/catalog/api"
import { messageOf } from "@/shared/api/errors"
import { saveNativeDownload } from "@/shared/download"
import { AppIconButton, AppMenu, useToast } from "@/shared/ui"
import type { MenuItem } from "@/shared/ui"

/**
 * What can be done, in one menu that keeps its shape.
 *
 * Every action the source has is a line, and the server decides which of them
 * are live: what changes a node waits for a node to be ticked, and what
 * changes what a node holds — a new folder, an upload, a table loaded from a
 * file — belongs to the place being looked at. Standing in a folder is not
 * choosing it, so nothing is renamed or removed because of where the user
 * happens to be. A source that has no actions at all shows no menu rather than
 * an empty one. See the spec, S6.
 */
const props = defineProps<{
  connectorId: string
  /**
   * Where something new would be made: the groupings whose contents are on
   * screen, or the level itself when the source offers none. `null` is the
   * root of the connector.
   */
  places: (string | null)[]
  /** The nodes that are ticked. */
  checkedIds: string[]
  placeLabel: string
  checkedLabel: string
}>()

const emit = defineEmits<{ done: [outcome: ActionOutcome] }>()
const toast = useToast()
const downloadAction = useDownloadAction()

const connectorId = computed(() => props.connectorId)

// The route takes null for the root and a non-empty list otherwise.
const placeIds = computed<string[] | null>(() => {
  const named = props.places.filter((id): id is string => id !== null && id !== "")
  return named.length === 0 ? null : named
})
const checkedIds = computed<string[] | null>(() =>
  props.checkedIds.length === 0 ? null : [...props.checkedIds]
)
const anyChecked = computed(() => props.checkedIds.length > 0)

// Two questions, because a menu line is about one of two subjects: the place
// being looked at, or what is ticked in it. The vocabulary is the same in both
// answers, so the first is enough to draw the menu before anything is ticked.
const here = useNodeActions(connectorId, placeIds)
const picked = useNodeActions(connectorId, checkedIds, anyChecked)

const commands = computed(() =>
  toMenu(here.data.value ?? [], picked.data.value ?? [], props.places, props.checkedIds)
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

const targetLabel = computed(() =>
  active.value?.actsOn === "children" ? props.placeLabel : props.checkedLabel
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
      @update:command="active = null"
      @done="emit('done', $event)"
    />
  </span>
</template>
