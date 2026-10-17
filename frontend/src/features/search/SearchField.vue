<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useTemplateRef, watch } from "vue"

import type { Hit } from "@/client"
import { askTheAgent } from "@/features/ai/state"
import { useWorkspaceActions } from "@/features/workspace/state"
import { t } from "@/shared/i18n"
import type { SearchScope } from "@/features/workspace/state"
import { AppCombobox, appIcons } from "@/shared/ui"
import type { SelectOption } from "@/shared/ui"
import { useRecentSearchesStore } from "@/stores/recentSearches"
import { useSpaceStore } from "@/stores/space"

import { EMPTY_ANSWER, nothingFound, pendingOf, withoutHits } from "./answer"
import { contextOf, placeOf } from "./context"
import { useForgetOpened, useHitActions, useRecentlyOpened } from "./openers"
import { nothingFoundSentence, stillSearching, typingNote } from "./outcomes"
import {
  ASK_OPTION,
  ASK_VALUE,
  fieldOptions,
  RECENT_PREFIX,
  RECENT_SEARCHES_HEADING,
  RECENTLY_OPENED_GROUP,
  RECENTLY_OPENED_HEADING,
  recentOptions,
  SCOPE_VALUE,
} from "./rows"
import { useFieldAnswer } from "./useAnswer"
import { MIN_CHARACTERS } from "./words"

/**
 * The search, opened over everything at the top of the window (D205).
 *
 * Over floating windows and the activity sheet, at a layer of its own: a
 * window may cover the header, and a field under it would take what is typed
 * blind. The list of what was found opens under it as a menu, above it.
 *
 * Its words outlive it: opened again, it shows them selected, so the next key
 * replaces them and Enter asks them again.
 */
const open = defineModel<boolean>("open", { required: true })

const props = defineProps<{
  /** The catalog that had the focus when the search was opened, as a scope to offer. */
  offer: SearchScope | null
}>()

const actions = useWorkspaceActions()
const recent = useRecentSearchesStore()
const space = useSpaceStore()
const hits = useHitActions()
const opened = useRecentlyOpened()
const forgetOpened = useForgetOpened()

const words = ref("")
const listOpen = ref(false)
/** The scope taken: that connection only, from where its catalog stood. */
const scope = ref<SearchScope | null>(null)
const box = useTemplateRef<InstanceType<typeof AppCombobox>>("box")
const root = useTemplateRef<HTMLElement>("root")
/** Where the focus was before: the second Escape gives it back. */
let returnTo: HTMLElement | null = null

const field = useFieldAnswer(words, () => ({
  context: contextOf(actions.activeConnectorId.value, actions.openConnectorIds.value),
  only: scope.value === null ? undefined : [placeOf(scope.value)],
  recent: opened(),
  browser: actions.browserPlaces(),
}))

const typed = computed(() => words.value.trim())
const asking = computed(() => typed.value.length >= MIN_CHARACTERS)

/**
 * Rows of what was opened lately that the person took out, hidden until the
 * empty field is answered again without them.
 */
const removed = ref<ReadonlySet<string>>(new Set())
watch(field.drawn, () => {
  removed.value = new Set()
})

/** The answer the list is drawn from, kept whole between two keys. */
const shown = computed(() => withoutHits(field.drawn.value ?? EMPTY_ANSWER, removed.value))

/** Each hit by the value of its row. */
const hitsByKey = computed(() => {
  const found = new Map<string, Hit>()
  for (const hit of shown.value.best ?? []) found.set(hit.key, hit)
  for (const cell of shown.value.cells) {
    for (const hit of cell.hits) if (!found.has(hit.key)) found.set(hit.key, hit)
  }
  return found
})

const offerRow = computed<SelectOption[]>(() =>
  props.offer === null || scope.value !== null
    ? []
    : [{ label: t("search.field.offer", { name: props.offer.label }), value: SCOPE_VALUE, icon: appIcons.search, offer: true }]
)

const options = computed<SelectOption[]>(() => [
  ...offerRow.value,
  ...(asking.value
    ? fieldOptions(shown.value)
    : [...recentOptions(recent.entries), ...(typed.value === "" ? fieldOptions(shown.value) : [])]),
])

/** The popup's last row, under Show all results: the words handed to a new chat (S10). */
const askRow = computed<SelectOption[]>(() => (asking.value ? [ASK_OPTION] : []))

const status = computed(() => {
  if (!asking.value) return ""
  if (field.error.value !== null) return field.error.value
  const live = field.live.value
  const waiting = pendingOf(live).length
  if (live.end === null && (live.mode === null || waiting > 0)) {
    return live.mode === null ? t("search.field.searching") : stillSearching(waiting)
  }
  const drawn = field.drawn.value
  if (drawn === null) return ""
  if (nothingFound(drawn) && drawn.end !== null) return nothingFoundSentence(drawn.end.asked)
  return typingNote(drawn.cells)
})

function show() {
  // Whatever had the focus a moment ago, unless it is this field already.
  const active = document.activeElement
  if (active instanceof HTMLElement && !root.value?.contains(active)) returnTo = active
  scope.value = null
  listOpen.value = true
  // Empty, it asks what was opened lately, which may have grown since.
  field.refresh()
  void nextTick(() => {
    box.value?.focus()
    box.value?.select()
  })
}

function close() {
  open.value = false
  listOpen.value = false
  field.cancel()
}

/** The second Escape: the person is leaving, back to where they were. */
function leave() {
  const back = returnTo
  close()
  returnTo = null
  if (back?.isConnected) back.focus()
}

watch(
  open,
  (now) => {
    if (now) show()
  },
  { immediate: true }
)

function takeScope() {
  if (props.offer === null) return
  scope.value = props.offer
  if (asking.value) field.refresh()
}

function removeScope() {
  scope.value = null
  if (asking.value) field.refresh()
}

function pick(value: string | number) {
  const key = String(value)
  if (key === SCOPE_VALUE) {
    takeScope()
    return
  }
  if (key === ASK_VALUE) {
    const asked = typed.value
    close()
    askTheAgent(asked)
    space.show("ai")
    return
  }
  if (key.startsWith(RECENT_PREFIX)) {
    words.value = key.slice(RECENT_PREFIX.length)
    return
  }
  const hit = hitsByKey.value.get(key)
  if (hit === undefined) return
  close()
  void hits.open(hit)
}

/** A row's own action: a node shown in its catalog rather than opened (D205). */
function act(value: string | number) {
  const hit = hitsByKey.value.get(String(value))
  if (hit === undefined) return
  close()
  void hits.showInCatalog(hit)
}

/** A row's cross or Delete, or a heading's Clear: out of the list, the list kept open. */
function remove(value: string | number) {
  const key = String(value)
  if (key === RECENT_SEARCHES_HEADING) {
    recent.clear()
    return
  }
  if (key.startsWith(RECENT_PREFIX)) {
    recent.forget(key.slice(RECENT_PREFIX.length))
    return
  }
  if (key === RECENTLY_OPENED_HEADING) {
    const group = shown.value.cells.filter((cell) => cell.planned.group.key === RECENTLY_OPENED_GROUP)
    removed.value = new Set([...removed.value, ...group.flatMap((cell) => cell.hits.map((hit) => hit.key))])
    forgetOpened.all()
  } else {
    const hit = hitsByKey.value.get(key)
    if (hit === undefined) return
    removed.value = new Set([...removed.value, key])
    forgetOpened.one(hit)
  }
  field.refresh()
}

/** Enter with no row chosen: everything, in the Search tab. */
function submit() {
  if (!asking.value) return
  actions.openSearch(
    { words: typed.value, scope: scope.value },
    { float: space.current !== "data" }
  )
  close()
}

// A press anywhere else puts the search away, the words kept. The list is a
// menu of its own outside this element, and a press in it is the search's.
function pressedOutside(event: PointerEvent) {
  const target = event.target
  if (!(target instanceof Node)) return
  if (root.value?.contains(target)) return
  if (target instanceof Element && target.closest(".q-menu") !== null) return
  close()
}

watch(
  open,
  (now) => {
    if (now) document.addEventListener("pointerdown", pressedOutside, true)
    else document.removeEventListener("pointerdown", pressedOutside, true)
  },
  { immediate: true }
)
onBeforeUnmount(() => document.removeEventListener("pointerdown", pressedOutside, true))

/** Asked for again while it is open: the words selected, the list shown. */
defineExpose({ show })
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      ref="root"
      class="search-field"
      role="search"
      data-testid="search-field"
    >
      <AppCombobox
        ref="box"
        v-model="words"
        v-model:open="listOpen"
        :label="t('search.field.label')"
        :placeholder="t('search.field.placeholder')"
        :options="options"
        :status="status"
        :chip="scope ? scope.label : null"
        :submit-label="asking ? t('search.field.show_all') : undefined"
        :trailing="askRow"
        data-testid="search-combobox"
        @pick="pick"
        @action="act"
        @remove="remove"
        @submit="submit"
        @remove-chip="removeScope"
        @leave="leave"
      />
    </div>
  </Teleport>
</template>

<style scoped>
/* Where the header's middle is, over whatever covers it. */
.search-field {
  position: fixed;
  top: calc((var(--dp-header-height) - var(--dp-control-height)) / 2);
  left: 50%;
  z-index: var(--dp-layer-search);
  width: min(640px, calc(100vw - 2 * var(--dp-space-4)));
  transform: translateX(-50%);
  border-radius: var(--dp-radius-control);
  box-shadow: 0 var(--dp-space-1) var(--dp-space-4) var(--dp-shadow);
}
</style>
