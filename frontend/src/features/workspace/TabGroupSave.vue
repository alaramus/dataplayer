<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

import { t } from "@/shared/i18n"
import { AppButton, AppTooltip } from "@/shared/ui"
import { useSpaceStore } from "@/stores/space"

import { groupNameProblem, groupsUnavailableIn, suggestedGroupName } from "./groups"
import TabGroupNameDialog from "./TabGroupNameDialog.vue"
import type { TabGroupLibrary } from "./useTabGroups"

/** The rail block that keeps the open layout as a tab group. */
const props = defineProps<{ groups: TabGroupLibrary }>()

const saving = ref(false)
const name = ref("")
const busy = computed(() => props.groups.busy.value)
const problem = computed(() => groupNameProblem(name.value, props.groups.groups.value))
const space = useSpaceStore()
const unavailable = computed(() => groupsUnavailableIn(space.current))

function ask() {
  if (!props.groups.canSave.value || unavailable.value !== null) return
  name.value = suggestedGroupName(props.groups.groups.value)
  saving.value = true
}

function save() {
  if (!problem.value && props.groups.save(name.value)) saving.value = false
}
</script>

<template>
  <!-- The tooltip hangs off a wrapper: a disabled Quasar button takes no
       pointer events, and greyed is when the reason is worth reading. -->
  <span class="tab-group-save">
    <AppButton
      variant="quiet"
      size="sm"
      :icon="appIcons.bookmarkAdd"
      :aria-label="t('workspace.groups.save')"
      :disable="busy || !groups.canSave.value || unavailable !== null"
      data-testid="save-tab-group"
      @click="ask"
    />
    <AppTooltip>
      {{ unavailable === null
        ? t('workspace.groups.save')
        : t('workspace.groups.save_unavailable', { reason: unavailable }) }}
    </AppTooltip>
  </span>
  <TabGroupNameDialog
    v-model="saving"
    v-model:name="name"
    :title="t('workspace.groups.save_title')"
    :problem="problem"
    :busy="busy"
    @confirm="save"
  />
</template>

<style scoped>
.tab-group-save {
  display: inline-flex;
  align-items: center;
}
</style>
