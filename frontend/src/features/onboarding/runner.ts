import { computed, reactive, readonly } from "vue"

import { BASICS } from "./basics"
import { settleMutation, settledByShown } from "./tour"
import type { Finder, MutationSuccess, TourChapter, TourMemory } from "./tour"

/**
 * The tour that is running, if any (D355).
 *
 * One per page and held in memory: the welcome starts it, Preferences starts
 * it again, and the host over the workspace draws it. A reload ends it.
 */
interface TourState {
  running: boolean
  chapters: readonly TourChapter[]
  chapter: number
  memory: TourMemory
}

const state = reactive<TourState>({
  running: false,
  chapters: BASICS,
  chapter: 0,
  memory: {},
})

export const tourState = readonly(state)

export const currentChapter = computed<TourChapter | null>(
  () => (state.running ? (state.chapters[state.chapter] ?? null) : null)
)

/** Every chapter done: the closing card is shown. */
export const tourFinished = computed(() => state.running && state.chapter >= state.chapters.length)

export function startTour(chapters: readonly TourChapter[] = BASICS) {
  state.chapters = chapters
  state.chapter = 0
  state.memory = {}
  state.running = true
}

export function endTour() {
  state.running = false
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
export function checkShown(find: Finder) {
  const chapter = currentChapter.value
  if (chapter === null) return
  if (settledByShown(chapter, state.memory, find)) advance(state.memory)
}
