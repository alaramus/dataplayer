import { computed, reactive, readonly } from "vue"

import { settleMutation, settledByShown } from "./tour"
import type { Counter, Finder, MutationSuccess, TourChapter, TourDefinition, TourMemory } from "./tour"

/**
 * The tour that is running, if any (D355).
 *
 * One per page and held in memory: the welcome, Preferences and a part of the
 * application opened for the first time start one, and the host over the
 * workspace draws it. A reload ends it.
 */
interface TourState {
  tour: TourDefinition | null
  /** The host is making what the tour needs before its first chapter. */
  preparing: boolean
  chapter: number
  memory: TourMemory
}

const state = reactive<TourState>({
  tour: null,
  preparing: false,
  chapter: 0,
  memory: {},
})

export const tourState = readonly(state)

export const runningTour = computed<TourDefinition | null>(() => state.tour)

export const currentChapter = computed<TourChapter | null>(() =>
  state.tour !== null && !state.preparing ? (state.tour.chapters[state.chapter] ?? null) : null
)

/** Every chapter done. */
export const tourFinished = computed(
  () => state.tour !== null && !state.preparing && state.chapter >= state.tour.chapters.length
)

export function startTour(tour: TourDefinition) {
  state.tour = tour
  state.chapter = 0
  state.memory = {}
  state.preparing = tour.setup !== undefined
}

/** What the tour made for itself is in place; the first chapter begins. */
export function prepared(memory: TourMemory) {
  state.memory = memory
  state.preparing = false
}

export function endTour() {
  state.tour = null
  state.preparing = false
}

function advance(memory: TourMemory) {
  state.memory = memory
  state.chapter += 1
}

/** A mutation succeeded somewhere on the page; it may be the one awaited. */
export function offerMutation(success: MutationSuccess) {
  const chapter = currentChapter.value
  if (chapter === null) return
  const memory = settleMutation(chapter, success, state.memory)
  if (memory !== null) advance(memory)
}

/** Read every frame: a chapter completed by a control appearing. */
export function checkShown(find: Finder, count?: Counter) {
  const chapter = currentChapter.value
  if (chapter === null) return
  if (settledByShown(chapter, state.memory, find, count)) advance(state.memory)
}

/** The hint's button, on a chapter that is only shown. */
export function nextChapter() {
  const chapter = currentChapter.value
  if (chapter?.done.kind === "next") advance(state.memory)
}
