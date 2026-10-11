<script setup lang="ts">
import { computed, ref, watch } from "vue"

import type { SearchRequest } from "@/client"
import { useConnectors } from "@/features/connectors/api"
import { useKeptLists } from "@/features/searchIndex/api"
import { useSearchIndexWindow } from "@/features/searchIndex/searchIndexWindow"
import { isKept, offersKeeping } from "@/features/searchIndex/state"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import type { SearchScope } from "@/features/workspace/state"
import {
  AppButton,
  AppEmptyState,
  AppIconButton,
  AppInput,
  AppOption,
  AppScrollArea,
  AppSelect,
  appIcons,
} from "@/shared/ui"
import type { SelectOption } from "@/shared/ui"
import { useRecentSearchesStore } from "@/stores/recentSearches"

import { foundSavedQueryText, nothingFound, pendingOf } from "./answer"
import { contentsChoices, contentsWordsOf } from "./contents"
import { contextOf, hintsOf, placeOf } from "./context"
import { useHitActions, useRecentlyOpened } from "./openers"
import { followOf, nothingFoundSentence, stillSearching } from "./outcomes"
import type { Gesture } from "./outcomes"
import { hitOption } from "./rows"
import SearchContents from "./SearchContents.vue"
import SearchOutcome from "./SearchOutcome.vue"
import { CHANGED_OPTIONS, filterChoices, foundCount, NO_FILTERS, tabGroups } from "./tab"
import type { ChangedWithin, SaidCell, TabFilters } from "./tab"
import { useTabAnswer } from "./useAnswer"
import { MIN_CHARACTERS } from "./words"

/**
 * The Search tab: the whole answer, drawn as each place answers (D205).
 *
 * Groups stand in the plan's fixed order from its first line, so a place that
 * answers late fills its own place and moves nothing already drawn. It keeps
 * no words of its own anywhere but here: they arrive with the request that
 * opened it, and a tab restored from a layout or a tab group is empty.
 */
const props = defineProps<{ panelId: string }>()

const actions = useWorkspaceActions()
const recent = useRecentSearchesStore()
const hitActions = useHitActions(() => props.panelId)
const opened = useRecentlyOpened()

const words = ref("")
const scope = ref<SearchScope | null>(null)
/** The words the answer on screen was asked for: the field may have moved on since. */
const asked = ref("")
const filters = ref<TabFilters>({ ...NO_FILTERS })
/** The search inside files whose matches are shown (S7). */
const contentsJob = ref<string | null>(null)

const tab = useTabAnswer(undefined, (state, searched) => {
  // Words that found a saved query's text are not kept (D205).
  if (foundSavedQueryText(state)) recent.forget(searched)
  else recent.remember(searched)
})
const answer = tab.state

function context(): string[] {
  return contextOf(actions.activeConnectorId.value, actions.openConnectorIds.value)
}

/**
 * Where the person is, what they opened lately — recency orders the best
 * matches (S6) — and the tabs and groups only the browser knows (S9).
 */
function around(): Pick<SearchRequest, "context" | "recent" | "browser"> {
  return { context: context(), ...hintsOf(opened(), actions.browserPlaces()) }
}

function search() {
  const typed = words.value.trim()
  if (typed.length < MIN_CHARACTERS) return
  if (typed !== asked.value) contentsJob.value = null
  asked.value = typed
  filters.value = { ...NO_FILTERS }
  const request: SearchRequest = {
    words: typed,
    mode: "search",
    lane: "tab",
    ...around(),
    ...(scope.value === null ? {} : { only: [placeOf(scope.value)] }),
  }
  void tab.search(request)
}

// Taken rather than read, so a tab brought forward later does not search the
// same words again by itself.
watch(
  actions.searchTarget,
  (target) => {
    if (target === null) return
    const taken = actions.takeSearch()
    if (taken === null) return
    const job = taken.contentsJob ?? null
    words.value = job === null ? taken.words : (contentsWordsOf(job) ?? taken.words)
    scope.value = taken.scope
    search()
    // After the search, which lets go of a job asked for other words.
    contentsJob.value = job
  },
  { immediate: true }
)

useReloadable(
  () => props.panelId,
  () => {
    if (asked.value === "") return
    words.value = asked.value
    search()
  }
)

function everywhere() {
  scope.value = null
  search()
}

const TRY_AGAIN: Gesture = { kind: "retry", label: "Try again" }

// A slow or stopped connection of one's own can keep its names (D212).
const connectors = useConnectors()
const keptLists = useKeptLists()
const searchIndexWindow = useSearchIndexWindow()
const keptIds = computed(
  () =>
    new Set(
      (keptLists.data.value?.lists ?? []).filter(isKept).map((state) => state.connector_id)
    )
)

function connectionOf(one: SaidCell) {
  const id = one.cell.planned.connector_id
  return connectors.data.value?.data.find((connector) => connector.id === id)
}

function offersKeep(one: SaidCell): boolean {
  const connection = connectionOf(one)
  return offersKeeping(
    one.cell.planned,
    one.cell.outcome,
    connection === undefined
      ? undefined
      : { owned: connection.access === "own", adapterType: connection.adapter_type },
    keptLists.data.value?.types ?? [],
    keptIds.value
  )
}

function keepNames(one: SaidCell) {
  const connection = connectionOf(one)
  if (connection) searchIndexWindow.open({ id: connection.id, name: connection.name })
}

/** A gesture on one place: that place asked again, beside the answer, never instead of it. */
function take(one: SaidCell) {
  const gesture = one.said.gesture
  if (gesture === null) return
  if (gesture.kind === "enter") {
    search()
    return
  }
  // Unlocked where it was said: the place is asked again.
  const request = followOf(gesture.kind === "unlock" ? TRY_AGAIN : gesture, asked.value, one.cell.planned, answer.value.cells)
  if (request === null || (request.only?.length ?? 0) === 0) return
  void tab.follow({ ...request, ...around() })
}

const now = ref(Date.now())
watch(answer, () => {
  now.value = Date.now()
})

const groups = computed(() => tabGroups(answer.value, filters.value, now.value))
const choices = computed(() => filterChoices(answer.value))
const pending = computed(() => pendingOf(answer.value).length)
const nothing = computed(() => nothingFound(answer.value))
const hasAnswer = computed(() => answer.value.mode !== null)
const insideChoices = computed(() => contentsChoices(answer.value))

const summary = computed(() => {
  if (tab.error.value !== null) return tab.error.value
  if (!hasAnswer.value) return tab.searching.value ? "Searching…" : ""
  if (pending.value > 0) return stillSearching(pending.value)
  if (nothing.value) return ""
  const count = foundCount(answer.value)
  return count === 1 ? "1 found" : `${String(count)} found`
})

const ALL = ""

function choicesWith(all: string, options: SelectOption[]): SelectOption[] {
  return [{ label: all, value: ALL }, ...options]
}

const groupOptions = computed(() => choicesWith("Any group", choices.value.groups))
const connectionOptions = computed(() => choicesWith("Any connection", choices.value.connections))
const kindOptions = computed(() => choicesWith("Any kind", choices.value.kinds))

function setFilter(key: "group" | "connection" | "kind", value: unknown) {
  filters.value = { ...filters.value, [key]: value === ALL || typeof value !== "string" ? null : value }
}

function setChanged(value: unknown) {
  filters.value = { ...filters.value, changed: (typeof value === "string" ? value : "any") as ChangedWithin }
}
</script>

<template>
  <div
    class="search-tab"
    data-testid="search-tab"
  >
    <div class="search-tab__head">
      <AppInput
        v-model="words"
        class="search-tab__words"
        compact
        clearable
        autocomplete="off"
        placeholder="Search everything"
        aria-label="Search everything"
        :prepend-icon="appIcons.search"
        data-testid="search-tab-words"
        @keyup.enter="search"
      />
      <span
        v-if="scope"
        class="search-tab__scope"
        data-testid="search-tab-scope"
      >
        <span class="search-tab__scope-label">in {{ scope.label }}</span>
        <AppIconButton
          :icon="appIcons.close"
          tooltip="Search everywhere"
          @click="everywhere"
        />
      </span>
      <AppButton
        v-if="tab.searching.value"
        variant="quiet"
        size="sm"
        label="Stop"
        data-testid="search-tab-stop"
        @click="tab.stop()"
      />
    </div>

    <div
      v-if="hasAnswer"
      class="search-tab__filters"
    >
      <AppSelect
        :model-value="filters.group ?? ALL"
        :options="groupOptions"
        compact
        label-hidden
        label="Group"
        data-testid="search-filter-group"
        @update:model-value="setFilter('group', $event)"
      />
      <AppSelect
        :model-value="filters.connection ?? ALL"
        :options="connectionOptions"
        compact
        label-hidden
        label="Connection"
        data-testid="search-filter-connection"
        @update:model-value="setFilter('connection', $event)"
      />
      <AppSelect
        :model-value="filters.kind ?? ALL"
        :options="kindOptions"
        compact
        label-hidden
        label="Kind"
        data-testid="search-filter-kind"
        @update:model-value="setFilter('kind', $event)"
      />
      <AppSelect
        :model-value="filters.changed"
        :options="CHANGED_OPTIONS"
        compact
        label-hidden
        label="Changed"
        data-testid="search-filter-changed"
        @update:model-value="setChanged($event)"
      />
    </div>

    <p
      class="search-tab__summary"
      role="status"
      data-testid="search-tab-summary"
    >
      {{ summary }}
    </p>

    <AppScrollArea class="search-tab__body dp-panel-scroll">
      <SearchContents
        v-model:job-id="contentsJob"
        :panel-id="panelId"
        :choices="insideChoices"
        :words="asked"
      />
      <AppEmptyState
        v-if="nothing && answer.end"
        :icon="appIcons.search"
        :text="nothingFoundSentence(answer.end.asked)"
        data-testid="search-nothing"
      />
      <AppEmptyState
        v-else-if="!hasAnswer && !tab.searching.value"
        :icon="appIcons.search"
        text="Type words and press Enter to search everything"
      />
      <section
        v-for="group in groups"
        :key="group.key"
        class="search-tab__group"
        :aria-label="group.title"
        :data-testid="`search-group-${group.key}`"
      >
        <h3 class="search-tab__group-title">
          <span class="search-tab__group-name">{{ group.title }}</span>
          <span
            v-if="group.pending"
            class="search-tab__pending"
          >Searching…</span>
        </h3>
        <SearchOutcome
          v-for="one in group.said"
          :key="one.cell.planned.key"
          :said="one.said"
          :connector-id="one.cell.planned.connector_id"
          :offer-keep="offersKeep(one)"
          @gesture="take(one)"
          @keep="keepNames(one)"
        />
        <AppOption
          v-for="hit in group.hits"
          :key="hit.key"
          :option="hitOption(hit)"
          clickable
          dense
          data-testid="search-hit"
          @click="hitActions.open(hit)"
          @action="hitActions.showInCatalog(hit)"
        />
      </section>
    </AppScrollArea>
  </div>
</template>

<style scoped>
.search-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: var(--dp-space-1);
  gap: var(--dp-space-1);
}
.search-tab__head,
.search-tab__filters {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--dp-space-2);
}
.search-tab__words {
  flex: 1 1 200px;
  min-width: 0;
}
/* As wide as the value they show, not a share of the row: stretched, "Every
   kind" stood in a box three times its width and the four rarely fitted on
   one line. Narrow, a long value ends in an ellipsis. */
.search-tab__filters > * {
  flex: 0 1 auto;
  min-width: 0;
}
.search-tab__scope {
  display: inline-flex;
  align-items: center;
  gap: var(--dp-space-1);
  max-width: 50%;
  padding-left: var(--dp-space-2);
  border-radius: var(--dp-radius-pill);
  background: var(--dp-selected-quiet);
  font-size: var(--dp-font-size-sm);
}
.search-tab__scope-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.search-tab__summary {
  flex: none;
  margin: 0;
  min-height: var(--dp-line-height-sm);
  padding: 0 var(--dp-space-2);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
  line-height: var(--dp-line-height-sm);
}
.search-tab__body {
  flex: 1;
  min-height: 0;
}
.search-tab__group + .search-tab__group {
  border-top: 1px solid var(--dp-border-faint);
}
.search-tab__group-title {
  display: flex;
  align-items: baseline;
  gap: var(--dp-space-2);
  margin: 0;
  padding: var(--dp-space-2) var(--dp-space-3) var(--dp-space-1);
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-xs);
  font-weight: 500;
  line-height: var(--dp-line-height-sm);
  text-transform: uppercase;
}
.search-tab__group-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.search-tab__pending {
  text-transform: none;
}
.search-tab :deep(.app-option__line) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
