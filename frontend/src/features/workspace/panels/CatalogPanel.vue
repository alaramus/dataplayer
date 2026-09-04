<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"

import CatalogActions from "@/features/catalog/CatalogActions.vue"
import CatalogList from "@/features/catalog/CatalogList.vue"
import KeyspaceTree from "@/features/catalog/KeyspaceTree.vue"
import { reloadedBy, replacementsOf } from "@/features/catalog/actions"
import type { ActionOutcome } from "@/features/catalog/actions"
import { useNodePathLoader } from "@/features/catalog/api"
import type { SearchScope } from "@/features/catalog/api"
import { rememberAnswer, shouldAsk } from "@/features/catalog/contentSearch"
import { useFadingMark } from "@/features/catalog/fadingMark"
import { locationOf } from "@/features/catalog/location"
import { searchSummary } from "@/features/catalog/search"
import { useSearchHistory } from "@/features/catalog/useSearchHistory"
import { useAdapterTypes } from "@/features/connectors/api"
import { useCatalogLevel } from "@/features/catalog/useCatalogLevel"
import { groupTitle, showsPath } from "@/features/catalog/nodes"
import type { ListNode } from "@/features/catalog/nodes"
import { useReloadable } from "@/features/workspace/reloadable"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf, statusOf } from "@/shared/api/errors"
import { useCurrentUser } from "@/shared/auth/currentUser"
import {
  AppBanner,
  AppButton,
  AppIconButton,
  AppInput,
  AppMenu,
  AppSelect,
  AppTooltip,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { useSourceChangesStore } from "@/stores/sourceChanges"
import { diagramNodes, MAX_RELATIONS } from "@/features/relationships/model"

const props = defineProps<{
  panelId: string
  connectorId: string
  title: string
  adapterType: string
}>()

const toast = useToast()
const confirm = useConfirm()
const workspace = useWorkspaceActions()
const connectorId = computed(() => props.connectorId)
const rootLabel = computed(() => props.title)
const level = useCatalogLevel(connectorId, rootLabel)
const me = useCurrentUser()
const history = useSearchHistory(
  computed(() => me.data.value?.id ?? null),
  connectorId,
  level.filter
)
const historyOpen = ref(false)
const historyItems = computed(() =>
  history.entries.value.map((query) => ({
    name: query,
    label: query,
    removeLabel: `Remove “${query}” from history`,
  }))
)
watch(history.entries, (entries) => {
  if (entries.length === 0) historyOpen.value = false
})

function selectHistory(query: string) {
  level.clearSearch()
  history.select(query)
}

/**
 * What a diagram would be drawn of: the ticks, or everything the filter left.
 *
 * A line of the actions menu like Details, so the scope is the same question
 * the rest of the menu asks — and the line is disabled, not hidden, while the
 * set is empty or larger than one diagram holds (D97).
 */
const diagramSelection = computed(() => diagramNodes(level.checkedNodes.value, level.items.value))
const drawsNodes = computed(() => level.items.value.some((node) => node.describable))
const drawableNodes = computed(() =>
  !level.loading.value &&
  diagramSelection.value.length > 0 &&
  diagramSelection.value.length <= MAX_RELATIONS
)
function showRelationships() {
  if (!drawableNodes.value) return
  workspace.openRelationships({ connectorId: props.connectorId, connectorName: props.title, adapterType: props.adapterType, nodes: diagramSelection.value })
}

/**
 * Whether the first level has come back.
 *
 * What the head shows follows from what the level holds, and before the first
 * answer it holds nothing — which reads the same as a level with nothing to
 * filter by. Deciding then would draw the path for one round trip and take it
 * away again on every source that does have groupings. `loading` cannot stand
 * in for this: it goes up on every later reload too, and the head would blink
 * each time.
 */
const answered = ref(false)

// The level that is on screen, not the root: the path and the ticks are where
// the user put them, and going back to the top is navigation rather than a
// refresh.
useReloadable(props.panelId, async () => {
  await level.reload(level.path.value[level.path.value.length - 1]?.id ?? null)
})

/**
 * Something else changed this connection, so this list is out of date (D66).
 *
 * A console dropping a table is in another panel, and this one holds its rows
 * rather than reading them through the query cache. Which nodes changed does
 * not have to be known here: the level re-reads where it is standing, which
 * is the only thing on screen.
 */
const changes = useSourceChangesStore()
watch(
  () => changes.lastChange(props.connectorId),
  async (at, before) => {
    if (at === 0 || at === before) return
    await level.reload(level.path.value[level.path.value.length - 1]?.id ?? null)
  }
)

/** Long enough for the eye to catch the row, short enough not to read as a
    state the row is in. */
const REVEAL_SECONDS = 3

/**
 * The node this catalog was told to point at.
 *
 * Taken from the workspace rather than passed in: the panel may have been
 * opened by the very press that asked for the pointing, so `immediate` is what
 * catches the target that was set before this existed.
 *
 * Where the node lives is asked of the source, which is the only party that
 * knows what its own ids are made of — see D21. Nothing here takes one apart.
 */
// Destructured so the template reads the ref directly: a ref reached through
// an object is not unwrapped there.
const {
  value: revealedNode,
  show: showRevealed,
  clear: clearReveal,
} = useFadingMark<string>(REVEAL_SECONDS * 1000)

const loadPath = useNodePathLoader()

/**
 * Stand where the node lives, then point at it.
 *
 * The path is asked for every time rather than only when the node is out of
 * sight: one road through the code instead of two, and the answer is cached,
 * so pointing at the same table twice costs one request. `showLocation` is
 * what decides whether anything moves — a level that is already the right one
 * keeps the user's ticks.
 *
 * The mark is set a tick later because putting the trail in place is itself a
 * change of level, and a change of level is what takes a mark off.
 */
async function reveal(nodeId: string, label: string) {
  try {
    await level.showLocation(locationOf(await loadPath(props.connectorId, nodeId)))
    await nextTick()
    showRevealed(nodeId)
  } catch (cause) {
    const status = statusOf(cause)
    if (status === 501) {
      // The source cannot walk back up. That is a fact about it rather than
      // an event, so nothing is said: the node is marked if it happens to be
      // on the level already, which is all this could do before D21.
      showRevealed(nodeId)
      return
    }
    if (status === 404) {
      // A tab outlives the table it shows. Worth a word: without one the
      // press looks like it did nothing.
      toast.info(`${label} is no longer in the catalog`)
      return
    }
    toast.error(messageOf(cause, "Could not find this node in the catalog"))
  }
}

/**
 * One chain for everything that moves the level.
 *
 * The first read and a pointing that arrived together with the panel would
 * otherwise race, and whichever lost would leave the catalog somewhere the
 * user did not ask for — the pointing is what opened the panel, so the two
 * start in the same breath. They run in the order they are queued here, which
 * is why the first read is queued in setup rather than on mount.
 */
let work: Promise<void> = Promise.resolve()

function queue(job: () => Promise<void>): Promise<void> {
  work = work.then(job, job)
  return work
}

void queue(async () => {
  try {
    await level.load()
  } finally {
    answered.value = true
  }
})

watch(
  workspace.revealTarget,
  () => {
    const target = workspace.takeReveal(props.connectorId)
    if (target !== null) void queue(() => reveal(target.nodeId, target.label))
  },
  { immediate: true }
)

// Pointing says "here it is", which stops being true the moment the level is
// no longer the one it was said about — sooner than the few seconds, if the
// user walks away in the meantime.
watch(
  () => level.path.value.map((crumb) => crumb.id).join("/"),
  () => {
    clearReveal()
  }
)

/**
 * What the level offers to look at, and what each one says about itself.
 *
 * The caption goes into the label because this control has nowhere else to
 * put one: "db3" and "db3 · 110 keys" are the difference between guessing
 * which database holds the data and being told.
 */
const groupOptions = computed(() =>
  level.groups.value.map((group) => ({
    label: group.caption === undefined ? group.label : `${group.label} · ${group.caption}`,
    value: group.id,
  }))
)

const showPath = computed(
  () => answered.value && showsPath(level.path.value.length, level.groups.value)
)

/** What the level is called, for a form that acts on the level itself. */
const levelLabel = computed(
  () => level.path.value[level.path.value.length - 1]?.label ?? props.title
)

/**
 * Where something new would be made, as the server names it.
 *
 * The groupings that are ticked, because their contents are what the list is
 * showing: a table is loaded into a schema, and a schema is a grouping here
 * rather than a folder one walks into. A source that offers no groupings — a
 * personal directory — puts new things in the level itself.
 */
const places = computed<(string | null)[]>(() =>
  level.selectedGroups.value.length > 0 ? [...level.selectedGroups.value] : [level.currentId.value]
)

const placeLabel = computed(() => {
  const chosen = level.groups.value.filter((group) => level.selectedGroups.value.includes(group.id))
  return chosen.length === 0 ? levelLabel.value : chosen.map((group) => group.label).join(", ")
})

/**
 * Every grouping this level offers, for a form that asks for one.
 *
 * All of them and not only what is ticked: moving a table means naming a
 * schema other than the one it is in, and the ticked ones are the schemas
 * being looked at.
 */
const groupings = computed(() =>
  level.groups.value.map((group) => ({
    id: group.id,
    label: group.label,
    system: group.system,
  }))
)

const selectedGroupNodes = computed(() =>
  level.groups.value
    .filter((group) => level.selectedGroups.value.includes(group.id))
    .map((group) => ({ id: group.id, label: group.label, kind: group.kind }))
)

/** What is ticked, in one phrase, for a form that acts on the ticked nodes. */
const checkedLabel = computed(() => {
  const ticked = level.checkedNodes.value
  if (ticked.length === 1) return ticked[0]?.label ?? ""
  return `${String(ticked.length)} items`
})

/**
 * The one ticked node the source will describe, or nothing.
 *
 * One, because a summary is about a node rather than about a selection. Which
 * nodes have one is the source's own answer, carried on the node (D75), so a
 * source that describes none never draws the line and a database's tables do
 * not offer a details tab that would answer 501.
 */
const describedNode = computed(() => {
  const ticked = level.checkedNodes.value
  if (ticked.length !== 1) return null
  const node = ticked[0]
  return node !== undefined && node.summarizable ? node : null
})

const describesNodes = computed(() => level.items.value.some((node) => node.summarizable))

function showDetails() {
  const node = describedNode.value
  if (node === null) return
  workspace.openSummary({
    connectorId: props.connectorId,
    nodeId: node.id,
    title: node.label,
    connectorName: props.title,
    adapterType: props.adapterType,
  })
}

/**
 * Whether this source can be searched at all.
 *
 * Read off the code the type catalog publishes, not off its name and not off
 * the wording of a capability: a title is written to be read, a code is a
 * promise (D76). The answer never changes while the app runs, so the query
 * behind it is fetched once.
 */
const adapterTypes = useAdapterTypes()
const sourceType = computed(() =>
  (adapterTypes.data.value ?? []).find((type) => type.name === props.adapterType)
)
const canSearch = computed(
  () => sourceType.value?.capabilities.some((one) => one.code === "search") === true
)

/**
 * Whether this source can be searched inside its files as well.
 *
 * Its own code, because it is its own promise: a database lists names and
 * cannot be grepped, and offering the gesture there would be offering a 501
 * (D76).
 */
const canSearchContents = computed(
  () => sourceType.value?.capabilities.some((one) => one.code === "content_search") === true
)

/**
 * Whether this catalog is expanded where it stands rather than walked.
 *
 * The source says which (D91), and this reads the answer: a screen that asked
 * "is this Redis" would be the old application. Everything the head offers —
 * a path, a set of groupings, a search — belongs to a level, so a tree shows
 * none of it and the menu is fed from the selection instead.
 */
const asTree = computed(() => sourceType.value?.catalog_shape === "tree")

/** What the tree has selected, which is one node or none. */
const picked = ref<ListNode | null>(null)
const pickedIsPlace = computed(
  () => picked.value !== null && picked.value.role !== "leaf"
)

/**
 * Where the tree is rooted: the one grouping that is on, or the top.
 *
 * The same choice a list makes with its schemas, made in the same control —
 * which is the point of D91's grouping being a grouping and not a folder.
 */
const treeRoot = computed<string | null>(
  () => level.selectedGroups.value[0] ?? null
)

/** Schemas, databases — the source's own word, read off the kind (D91). */
const groupsLabel = computed(() => groupTitle(level.groups.value))

/**
 * Whether the level's groupings are looked at one at a time.
 *
 * A tree has one root. Several schemas listed together are one list with a
 * column saying where each row came from; several key spaces expanded together
 * would be one tree with no such column, and nothing joins them anyway.
 */
const oneGroupOnly = computed(() => asTree.value)

/** The one grouping a tree stands in, named as the source names it. */
const groupLabel = computed(
  () =>
    level.groups.value.find((group) => group.id === treeRoot.value)?.label ??
    props.title
)

/** One control, whichever shape it is in: a list of ids either way. */
function pickGroups(chosen: unknown) {
  const ids = Array.isArray(chosen) ? (chosen as string[]) : [chosen as string]
  void level.setGroups(ids.filter((id) => id !== null && id !== undefined))
}

/**
 * Where something new would be made in a tree.
 *
 * The selected branch, or the root of the tree when a leaf is selected or
 * nothing is: a client cannot derive the branch a leaf hangs under, because an
 * id is the source's own string and is never taken apart here (D21).
 */
const treeLevelId = computed(() =>
  pickedIsPlace.value ? (picked.value?.id ?? null) : treeRoot.value
)
const treeChecked = computed(() =>
  picked.value !== null && !pickedIsPlace.value ? [picked.value] : []
)
const tree = ref<{ reload: () => Promise<void> } | null>(null)

/** Offered once there is something to look for, exactly as a filter is. */
const canRunSearch = computed(() => canSearch.value && level.filter.value.trim() !== "")

/** The button says what the second gesture does; nothing else would. */
const searchTooltip = computed(() =>
  canSearchContents.value
    ? "Search names below this folder — hold Shift to search inside the files"
    : "Search everything below this folder"
)

const foundText = computed(() => {
  const found = level.found.value
  return found === null ? "" : searchSummary(found)
})

/**
 * Search, by name or — held down — inside the files themselves.
 *
 * Shift on the same button rather than a second one: it is the same words in
 * the same field looked for in a second place, and a source that cannot read
 * its files simply never sees the difference.
 */
async function runSearch(event?: MouseEvent | KeyboardEvent) {
  history.remember(true)
  if (!canRunSearch.value) return
  const scope: SearchScope =
    event?.shiftKey === true && canSearchContents.value ? "contents" : "names"
  if (scope === "contents" && !(await agreedToRead())) return
  await level.search(scope)
}

/**
 * Ask once before reading everything below the folder.
 *
 * Minutes rather than milliseconds, and a keypress is a small gesture for it,
 * so the first one explains itself and offers to stop explaining. The answer
 * is this browser's — see `contentSearch.ts`.
 */
async function agreedToRead(): Promise<boolean> {
  if (!shouldAsk(localStorage)) return true
  return await confirm({
    title: "Search inside files",
    message:
      "Every file below this folder will be opened and read, which can take " +
      "minutes. Binary files and files over 8 MB are skipped.",
    confirmLabel: "Search inside",
    rememberLabel: "Do not ask again",
    onRemember: () => {
      rememberAnswer(localStorage, false)
    },
  })
}

/**
 * Open what a search found.
 *
 * A folder is walked into, which means standing where it lives first: the
 * trail has to say where we are, and only the source knows the way down to it
 * (D21). A file opens its tab and the results stay, because finding six of
 * them and being thrown back to a folder after the first is not a search.
 */
async function openFound(node: ListNode) {
  history.remember()
  if (node.role !== "container") {
    onOpen(node)
    return
  }
  try {
    await level.showLocation(locationOf(await loadPath(props.connectorId, node.id)))
    await level.enter(node)
  } catch (cause) {
    toast.error(messageOf(cause, `Could not open ${node.label}`))
  }
}

/** A click opens what can be read and walks into what cannot. */
function onOpen(node: ListNode) {
  // Remember before navigation can clear the field ahead of its blur event.
  history.remember()
  if (node.role === "container") {
    void level.enter(node)
    return
  }
  if (node.readable) {
    workspace.openRepresentation({
      connectorId: props.connectorId,
      nodeId: node.id,
      title: node.label,
      connectorName: props.title,
      adapterType: props.adapterType,
      representations: node.representations,
      describable: node.describable,
      // A node that opens and also holds nodes is a container of tables — a
      // workbook — so the tab it makes can offer the rest of them (D51).
      containerId: node.holdsNodes ? node.id : undefined,
    })
    return
  }
  // Said rather than left silent: a picture opens no tab, and without a word
  // the click looks like it did nothing at all.
  toast.info(`${node.label} has no viewer yet`)
}

function onToggle(id: string, on: boolean) {
  level.checked.value = on
    ? [...level.checked.value, id]
    : level.checked.value.filter((other) => other !== id)
}

async function afterAction(outcome: ActionOutcome) {
  for (const replacement of replacementsOf(outcome)) {
    level.replaceNode(replacement)
    workspace.replaceNode(props.connectorId, replacement)
  }
  const branches = reloadedBy(outcome)
  if (asTree.value) {
    // A tree has one reading rather than a level: which branches changed is
    // still the server's answer, and re-reading the whole of a bounded
    // catalog is cheaper than keeping a map of what is open in step with it.
    //
    // The level goes first even though nothing of it is drawn as a list. It
    // is what forgets the branches — a loader answering from a fresh cache
    // would hand back exactly what was asked to be replaced — and it is also
    // what re-reads the groupings, so a database that has just gained its
    // first key stops saying it is empty.
    if (branches.length > 0) {
      await level.reloadMany(branches)
      await tree.value?.reload()
    }
    return
  }
  if (branches.length > 0) await level.reloadMany(branches)
}
</script>

<template>
  <div class="catalog-panel">
    <div class="catalog-panel__head">
      <div class="catalog-panel__bar">
        <!-- Where we are, on the same line as the menu, not a stack of
             lines. Starting at a home button rather than at the name of the
             connection — the name is on the tab above, and what the first step
             of a path means is "back to the top". Whether it is drawn at all
             follows from what the level holds and never from the type of the
             source: see `showsPath` in `nodes.ts`. -->
        <div
          v-if="showPath && !asTree"
          class="catalog-panel__crumbs"
          data-testid="catalog-path"
        >
          <AppIconButton
            icon="home"
            tooltip="The top of this connection"
            :disable="level.path.value.length < 2"
            data-testid="catalog-home"
            @click="level.goTo(0)"
          />
          <!-- The trail scrolls and the home button does not: a path deep
               enough to run out of the column must not carry away the one
               step that always gets back. -->
          <div class="catalog-panel__trail">
            <template
              v-for="(crumb, index) in level.path.value.slice(1)"
              :key="index"
            >
              <q-icon
                name="chevron_right"
                size="14px"
                class="catalog-panel__chevron"
              />
              <span
                class="catalog-panel__crumb"
                :class="{ 'catalog-panel__crumb--last': index === level.path.value.length - 2 }"
                role="button"
                tabindex="0"
                @click="level.goTo(index + 1)"
                @keydown.enter="level.goTo(index + 1)"
              >{{ crumb.label }}</span>
            </template>
          </div>
        </div>

        <!-- Beside the path and not under it. The line answers one question —
             where we are inside this source — and the answer takes the shape
             the level's own nodes give it: a path for a directory, a set of
             groupings for a database. Which of the two shows follows from the
             nodes, never from the type of the source. -->
        <!-- Named only while nothing is picked. A chosen schema is a chip
             saying its own name, and the word above it is both a repetition
             and a second line in a bar that has one — Quasar floats a label
             out of the field exactly when the field is filled. -->
        <AppSelect
          v-if="groupOptions.length"
          class="catalog-panel__groups"
          :model-value="oneGroupOnly ? treeRoot : level.selectedGroups.value"
          :options="groupOptions"
          :label="level.selectedGroups.value.length ? undefined : groupsLabel"
          :aria-label="groupsLabel"
          :multiple="!oneGroupOnly"
          compact
          data-testid="catalog-groups"
          @update:model-value="pickGroups"
        />

        <!-- One menu, fed from wherever the selection lives: a level's ticks
             or a tree's one selected node. What an action may do to them is
             still the server's answer about those nodes. -->
        <CatalogActions
          v-if="asTree"
          class="catalog-panel__menu"
          :connector-id="connectorId"
          :level-id="treeLevelId"
          :level-label="picked?.label ?? groupLabel"
          :places="[treeLevelId]"
          :selected-groups="[]"
          :groupings="[]"
          :checked-ids="treeChecked.map((node) => node.id)"
          :checked-nodes="treeChecked.map((node) => ({ label: node.label, kind: node.kind }))"
          :place-label="picked && pickedIsPlace ? picked.label : groupLabel"
          :checked-label="treeChecked[0]?.label ?? ''"
          :describes-nodes="false"
          :described-node="null"
          :draws-nodes="false"
          :drawable-nodes="false"
          @done="afterAction"
          @details="showDetails"
        />
        <CatalogActions
          v-else
          class="catalog-panel__menu"
          :connector-id="connectorId"
          :level-id="level.currentId.value"
          :level-label="levelLabel"
          :places="places"
          :selected-groups="selectedGroupNodes"
          :groupings="groupings"
          :checked-ids="level.checked.value"
          :checked-nodes="level.checkedNodes.value.map((node) => ({ label: node.label, kind: node.kind }))"
          :place-label="placeLabel"
          :checked-label="checkedLabel"
          :describes-nodes="describesNodes"
          :described-node="describedNode"
          :draws-nodes="drawsNodes"
          :drawable-nodes="drawableNodes"
          @done="afterAction"
          @details="showDetails"
          @relationships="showRelationships"
        />
      </div>

      <!-- On a line of its own: a filter is something a user types into, and
           typing needs the width. The same words are what a search looks for,
           so the button appears beside them rather than somewhere else with a
           field of its own (D76). -->
      <AppInput
        v-if="!asTree"
        v-model="level.filter.value"
        :placeholder="canSearch ? 'Filter, or search below' : 'Filter'"
        compact
        clearable
        data-testid="catalog-filter"
        @blur="history.remember()"
        @keyup.enter="runSearch"
      >
        <template #after>
          <AppButton
            variant="quiet"
            size="sm"
            icon="history"
            aria-label="Search history"
            aria-haspopup="menu"
            :aria-expanded="historyOpen"
            :disable="history.entries.value.length === 0 && level.filter.value.trim() === ''"
            data-testid="catalog-search-history"
            @click="history.remember()"
          >
            <AppTooltip>Search history</AppTooltip>
            <AppMenu
              v-model="historyOpen"
              :items="historyItems"
              @select="selectHistory"
              @remove="history.remove"
            />
          </AppButton>
          <AppIconButton
            v-if="canRunSearch"
            icon="search"
            :tooltip="searchTooltip"
            :loading="level.searching.value"
            data-testid="catalog-search"
            @click="runSearch"
          />
        </template>
      </AppInput>
    </div>

    <AppBanner
      v-if="level.error.value"
      tone="error"
      data-testid="catalog-error"
    >
      {{ level.error.value }}
    </AppBanner>

    <!-- While this is here the list is not a level, so it says what it is
         showing and offers the way back to the folder. -->
    <div
      v-if="level.found.value"
      class="catalog-panel__found"
      data-testid="catalog-search-summary"
    >
      <q-icon
        name="search"
        size="14px"
      />
      <span class="catalog-panel__found-text">{{ foundText }}</span>
      <AppIconButton
        icon="close"
        tooltip="Back to the folder"
        data-testid="catalog-search-close"
        @click="level.clearSearch"
      />
    </div>

    <AppBanner
      v-if="level.found.value?.notice"
      tone="info"
      data-testid="catalog-search-notice"
    >
      {{ level.found.value.notice }}
    </AppBanner>

    <KeyspaceTree
      v-if="asTree"
      ref="tree"
      class="catalog-panel__body"
      :connector-id="connectorId"
      :root-id="treeRoot"
      @select="picked = $event"
      @open="onOpen"
    />

    <CatalogList
      v-else
      class="catalog-panel__body"
      :items="level.items.value"
      :checked="level.checked.value"
      :loading="level.loading.value"
      :show-group="level.selectedGroups.value.length > 1"
      :has-parent="level.path.value.length > 1"
      :revealed="revealedNode"
      @open="level.found.value ? openFound($event) : onOpen($event)"
      @up="level.up"
      @toggle="onToggle"
      @toggle-all="level.toggleAll"
    />
  </div>
</template>

<style scoped>
.catalog-panel__found {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px 2px 8px;
  font-size: 11px;
  color: var(--dp-text-muted);
  border-bottom: 1px solid var(--dp-border-faint);
  flex: none;
}
.catalog-panel__found-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

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
/* One line of one height, whatever the source puts in it.
   A button and the menu are 32px, a field is 40, and a source with no
   groupings puts neither — so the height is stated here rather than left to
   be whatever the tallest thing in it happens to be. Moving between two
   connections must not move the list under them, and a rule about the panel
   is the only kind that a source type added later cannot break: what it
   brings centres in this line instead of setting it. */
.catalog-panel__bar {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 40px;
}
.catalog-panel__crumbs {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
  padding-right: 6px;
  border-radius: 999px;
  background: var(--dp-hover);
  font-size: 12px;
}
/* Takes what the line has left, and gives it back rather than pushing the
   menu off the end: the choice of schemas is a list of names, and a long one
   must not cost the column its only menu. */
.catalog-panel__groups {
  flex: 1;
  min-width: 0;
}
/* The menu keeps to the end of the line whether or not there is a path to
   push it there. */
.catalog-panel__menu {
  margin-left: auto;
}
.catalog-panel__trail {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  overflow-x: auto;
  white-space: nowrap;
  /* No bar: it would be thicker than the line it sits in. The path is
     scrolled by wheel or touch, and every step of it is also a click. */
  scrollbar-width: none;
}
.catalog-panel__trail::-webkit-scrollbar {
  display: none;
}
.catalog-panel__crumb,
.catalog-panel__chevron {
  flex: none;
}
.catalog-panel__crumb {
  cursor: pointer;
  padding: 2px 2px;
  color: var(--dp-link);
}
.catalog-panel__crumb--last {
  cursor: default;
  font-weight: 500;
  color: var(--dp-text-strong);
}
.catalog-panel__chevron {
  color: var(--dp-text-faint);
}
.catalog-panel__body {
  flex: 1;
  min-height: 0;
}
</style>
