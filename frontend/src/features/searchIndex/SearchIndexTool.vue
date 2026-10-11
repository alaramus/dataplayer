<script setup lang="ts">
import { computed } from "vue"

import type { KeepState } from "@/client"
import { useKeptLists, useRefreshKeep } from "@/features/searchIndex/api"
import { useSearchIndexWindow } from "@/features/searchIndex/searchIndexWindow"
import { statusLine, windowName } from "@/features/searchIndex/state"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppEmptyState,
  AppIconButton,
  AppSpinner,
  appIcons,
  useToast,
} from "@/shared/ui"

/**
 * Every connection whose names are kept for search, a tool of the panel at the
 * foot of the screen (D212, D143): its state, its age and Read now. Choosing
 * which connections keep a list is done from each catalog's Actions menu, or
 * from Settings here.
 */
const lists = useKeptLists()
const refresh = useRefreshKeep()
const window = useSearchIndexWindow()
const toast = useToast()

const rows = computed<KeepState[]>(() => lists.data.value?.lists ?? [])

async function readAgain(state: KeepState) {
  try {
    await refresh.mutateAsync(state.connector_id)
  } catch (cause) {
    toast.error(messageOf(cause, "The names could not be asked for again"))
  }
}
</script>

<template>
  <div
    class="search-index-tool"
    data-testid="search-index-tool"
  >
    <AppSpinner v-if="lists.isLoading.value" />
    <AppBanner
      v-else-if="lists.isError.value"
      tone="warning"
    >
      {{ messageOf(lists.error.value, "The search index could not be read") }}
    </AppBanner>
    <AppEmptyState
      v-else-if="rows.length === 0"
      :icon="appIcons.manageSearch"
      text="No connection keeps its names yet. Choose Search index… in a catalog's Actions menu to find a large one by name at once."
    />
    <ul
      v-else
      class="search-index-tool__list"
    >
      <li
        v-for="state in rows"
        :key="state.connector_id"
        class="search-index-tool__row"
        :data-testid="`search-index-row-${state.connector_id}`"
      >
        <div class="search-index-tool__what">
          <span class="search-index-tool__name">{{ state.name }}</span>
          <span class="dp-helper">
            {{ statusLine(state) }}
          </span>
        </div>
        <span class="dp-helper search-index-tool__window">
          Within {{ windowName(state.window_seconds) }}
        </span>
        <span class="dp-helper search-index-tool__owner">
          {{ state.owner_email ?? "" }}
        </span>
        <AppButton
          v-if="state.may_change"
          variant="secondary"
          size="sm"
          label="Read now"
          :disable="state.status === 'reading' || state.refresh_asked === true"
          @click="readAgain(state)"
        />
        <AppIconButton
          :icon="appIcons.settings"
          :tooltip="state.may_change ? 'Search index settings' : 'What is kept'"
          :data-testid="`search-index-open-${state.connector_id}`"
          @click="window.open({ id: state.connector_id, name: state.name })"
        />
      </li>
    </ul>
  </div>
</template>

<style scoped>
.search-index-tool {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: auto;
  padding: var(--dp-space-2) var(--dp-space-3);
}
.search-index-tool__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.search-index-tool__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto auto;
  align-items: center;
  gap: var(--dp-space-3);
  padding: var(--dp-space-2) 0;
  border-bottom: 1px solid var(--dp-border);
}
.search-index-tool__what {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.search-index-tool__name {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
