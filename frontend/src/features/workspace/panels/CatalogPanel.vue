<script setup lang="ts">
import { computed, onMounted } from "vue"

import CatalogActions from "@/features/catalog/CatalogActions.vue"
import CatalogList from "@/features/catalog/CatalogList.vue"
import { useCatalogLevel } from "@/features/catalog/useCatalogLevel"
import type { ListNode } from "@/features/catalog/nodes"
import { adapterIcon } from "@/features/connectors/adapters"
import { useWorkspaceActions } from "@/features/workspace/state"
import { AppBanner, AppIconButton, AppInput, AppSelect, useToast } from "@/shared/ui"

const props = defineProps<{
  connectorId: string
  title: string
  adapterType: string
}>()

const toast = useToast()
const workspace = useWorkspaceActions()
const connectorId = computed(() => props.connectorId)
const rootLabel = computed(() => props.title)
const level = useCatalogLevel(connectorId, rootLabel)

onMounted(() => {
  void level.load()
})

const groupOptions = computed(() =>
  level.groups.value.map((group) => ({ label: group.label, value: group.id }))
)

/** What the actions apply to: what is ticked, or the level being looked at. */
const targets = computed<(string | null)[]>(() =>
  level.checked.value.length > 0 ? [...level.checked.value] : [level.currentId.value]
)

const targetLabel = computed(() => {
  const ticked = level.checkedNodes.value
  if (ticked.length === 1) return ticked[0]?.label ?? ""
  if (ticked.length > 1) return `${String(ticked.length)} items`
  return level.path.value[level.path.value.length - 1]?.label ?? props.title
})

/** A click opens what can be read and walks into what cannot. */
function onOpen(node: ListNode) {
  if (node.role === "container") {
    void level.enter(node)
    return
  }
  if (node.readable) {
    workspace.openRows(props.connectorId, node.id, node.label)
    return
  }
  // Said rather than left silent: a picture opens no tab, and without a word
  // the click looks like it did nothing at all.
  toast.info(`${node.label} cannot be read as rows`)
}

function onToggle(id: string, on: boolean) {
  level.checked.value = on
    ? [...level.checked.value, id]
    : level.checked.value.filter((other) => other !== id)
}

async function afterAction(reloadNodeIds: (string | null)[]) {
  for (const nodeId of reloadNodeIds) await level.reload(nodeId)
}
</script>

<template>
  <div class="catalog-panel">
    <div class="catalog-panel__head">
      <div class="catalog-panel__bar">
        <AppIconButton
          :icon="adapterIcon(adapterType)"
          tooltip="Edit connection"
          data-testid="catalog-connector"
          @click="workspace.editConnector(connectorId)"
        />
        <span class="catalog-panel__title">{{ title }}</span>

        <AppIconButton
          icon="arrow_upward"
          tooltip="Up one level"
          :disable="level.path.value.length < 2"
          data-testid="catalog-up"
          @click="level.up"
        />
        <CatalogActions
          :connector-id="connectorId"
          :node-ids="targets"
          :target-label="targetLabel"
          @done="afterAction"
        />
      </div>

      <!-- Whether this is a path or a set of groupings follows from the kinds
           of node the level holds, never from the type of the source. -->
      <div
        v-if="level.path.value.length > 1"
        class="catalog-panel__crumbs"
        data-testid="catalog-path"
      >
        <template
          v-for="(crumb, index) in level.path.value"
          :key="index"
        >
          <span
            v-if="index > 0"
            class="catalog-panel__slash"
          >/</span>
          <span
            class="catalog-panel__crumb"
            :class="{ 'catalog-panel__crumb--last': index === level.path.value.length - 1 }"
            role="button"
            tabindex="0"
            @click="level.goTo(index)"
            @keydown.enter="level.goTo(index)"
          >{{ crumb.label }}</span>
        </template>
      </div>

      <AppSelect
        v-if="groupOptions.length"
        :model-value="level.selectedGroups.value"
        :options="groupOptions"
        label="Schemas"
        multiple
        compact
        data-testid="catalog-groups"
        @update:model-value="level.setGroups($event as string[])"
      />

      <AppInput
        v-model="level.filter.value"
        placeholder="Filter"
        compact
        data-testid="catalog-filter"
      />
    </div>

    <AppBanner
      v-if="level.error.value"
      tone="error"
      data-testid="catalog-error"
    >
      {{ level.error.value }}
    </AppBanner>

    <CatalogList
      class="catalog-panel__body"
      :items="level.items.value"
      :checked="level.checked.value"
      :loading="level.loading.value"
      :show-group="level.selectedGroups.value.length > 1"
      @open="onOpen"
      @toggle="onToggle"
      @toggle-all="level.toggleAll"
    />
  </div>
</template>

<style scoped>
/* The panel is a box of the height the section gave it: the head stays and
   only the list moves. See the spec, S10. */
.catalog-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.catalog-panel__head {
  flex: none;
  padding: 4px 4px 0;
}
.catalog-panel__bar {
  display: flex;
  align-items: center;
  gap: 4px;
}
.catalog-panel__title {
  flex: 1;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.catalog-panel__crumbs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  padding: 0 4px 2px;
  font-size: 11px;
}
.catalog-panel__crumb {
  cursor: pointer;
  color: rgba(25, 118, 210, 0.9);
}
.catalog-panel__crumb--last {
  cursor: default;
  color: rgba(0, 0, 0, 0.6);
}
.catalog-panel__slash {
  color: rgba(0, 0, 0, 0.35);
}
.catalog-panel__body {
  flex: 1;
  min-height: 0;
}
</style>
