import { getCurrentScope, onScopeDispose, ref, shallowRef, watch } from "vue"
import type { Ref, ShallowRef } from "vue"

import type { BrowserPlace, RecentTarget, SearchRequest } from "@/client"

import { hintsOf } from "./context"
import { EMPTY_ANSWER, pendingOf, reduceAnswer, reduceFollow, settleFollow, stopPending } from "./answer"
import type { AnswerState } from "./answer"
import { askSearch, SearchRefused } from "./stream"
import type { SearchLine } from "./stream"
import { DEBOUNCE_MS, MIN_CHARACTERS } from "./words"

/** How an answer is asked for: the stream reader, or a stand-in in a test. */
export type Ask = (request: SearchRequest, signal: AbortSignal) => AsyncIterable<SearchLine>

function refusalOf(cause: unknown): string {
  if (cause instanceof SearchRefused) {
    return cause.status === 404 ? "That connection can't be searched any more" : cause.message
  }
  return "The search could not be run"
}

function stopWithOwner(stop: () => void) {
  if (getCurrentScope() !== undefined) onScopeDispose(stop)
}

/** What the field asks besides the words: where the person is (D200, D205). */
export interface FieldContext {
  context: string[]
  only: SearchRequest["only"]
  /** What was opened from the search lately, newest first (S6). */
  recent?: RecentTarget[]
  /** The open tabs and saved tab groups (S9). */
  browser?: BrowserPlace[]
}

/**
 * The field's answer to what is being typed (D200).
 *
 * Asked 150 ms after the last key and from two characters, in mode typing on
 * the field's own lane, each ask aborting the one before it — in the browser,
 * and so on the server. `drawn` is the last answer whose best matches are in:
 * the field draws whole answers, so a list does not empty between two keys
 * nor jump when the best matches arrive.
 *
 * An empty field asks with no words and what was opened lately, which the
 * server answers with those of them the person may still see (S6). A scope
 * is not sent with it: it narrows names, and an empty search names none.
 */
export function useFieldAnswer(
  words: Ref<string>,
  around: () => FieldContext,
  ask: Ask = askSearch
): {
  live: ShallowRef<AnswerState>
  drawn: ShallowRef<AnswerState | null>
  error: Ref<string | null>
  /** Ask again now, with the same words: a scope was taken or removed. */
  refresh: () => void
  cancel: () => void
} {
  const live = shallowRef<AnswerState>(EMPTY_ANSWER)
  const drawn = shallowRef<AnswerState | null>(null)
  const error = ref<string | null>(null)
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  // Whether `drawn` answers an empty field: what was opened lately is never
  // drawn as the answer to words, nor the other way round.
  let drawnEmpty = false

  function cancel() {
    controller?.abort()
    controller = null
    if (timer !== null) clearTimeout(timer)
    timer = null
  }

  function forget() {
    live.value = EMPTY_ANSWER
    drawn.value = null
    error.value = null
  }

  async function run(typed: string, request: SearchRequest) {
    const own = new AbortController()
    controller = own
    let state = EMPTY_ANSWER
    try {
      for await (const line of ask(request, own.signal)) {
        if (own.signal.aborted) return
        state = reduceAnswer(state, line)
        live.value = state
        if (state.best !== null || line.type === "end") {
          drawn.value = state
          drawnEmpty = typed === ""
        }
      }
      error.value = null
    } catch (cause) {
      if (own.signal.aborted) return
      error.value = refusalOf(cause)
      drawn.value = null
    }
  }

  function requestOf(typed: string): SearchRequest | null {
    const { context, only, recent = [], browser = [] } = around()
    const hint = hintsOf(recent, browser)
    if (typed === "") {
      return recent.length === 0 ? null : { words: "", mode: "typing", lane: "field", context, ...hint }
    }
    if (typed.length < MIN_CHARACTERS) return null
    return { words: typed, mode: "typing", lane: "field", context, ...(only ? { only } : {}), ...hint }
  }

  function schedule(delay: number) {
    cancel()
    const typed = words.value.trim()
    const request = requestOf(typed)
    if (request === null) {
      forget()
      return
    }
    if (drawnEmpty !== (typed === "")) forget()
    timer = setTimeout(() => {
      timer = null
      void run(typed, request)
    }, typed === "" ? 0 : delay)
  }

  watch(words, () => schedule(DEBOUNCE_MS))
  stopWithOwner(cancel)
  return { live, drawn, error, refresh: () => schedule(0), cancel }
}

/**
 * The Search tab's answer: one search on the tab's lane, and the follow-ups
 * its gestures ask on theirs, folded into it (D200, D201).
 *
 * A new search ends everything the last one was still asking. A follow-up is
 * one at a time, as the server keeps one answer per person and lane: a newer
 * one ends the older, whose places say again what they said before it.
 */
export function useTabAnswer(
  ask: Ask = askSearch,
  onEnd: (state: AnswerState, words: string) => void = () => undefined
): {
  state: ShallowRef<AnswerState>
  error: Ref<string | null>
  searching: Ref<boolean>
  search: (request: SearchRequest) => Promise<void>
  follow: (request: SearchRequest) => Promise<void>
  /** The person stopped it: what was still being asked says so. */
  stop: () => void
} {
  const state = shallowRef<AnswerState>(EMPTY_ANSWER)
  const error = ref<string | null>(null)
  const searching = ref(false)
  let main: AbortController | null = null

  interface Following {
    controller: AbortController
    /** The answer as it stood when the follow-up was asked. */
    before: AnswerState
    /** The cells its plan put back to pending. */
    asked: Set<string>
  }
  let following: Following | null = null

  function endFollow() {
    const one = following
    if (one === null) return
    following = null
    one.controller.abort()
    state.value = settleFollow(one.before, state.value, one.asked)
  }

  function cancel() {
    main?.abort()
    main = null
    following?.controller.abort()
    following = null
    searching.value = false
  }

  function stop() {
    endFollow()
    if (main !== null) {
      main.abort()
      main = null
      state.value = stopPending(state.value)
    }
    searching.value = false
  }

  async function search(request: SearchRequest) {
    cancel()
    const own = new AbortController()
    main = own
    state.value = EMPTY_ANSWER
    error.value = null
    searching.value = true
    try {
      for await (const line of ask(request, own.signal)) {
        if (own.signal.aborted) return
        state.value = reduceAnswer(state.value, line)
      }
      // An answer another of the person's tabs took the place of ends with
      // no line for what it was still asking.
      if (pendingOf(state.value).length > 0) state.value = stopPending(state.value)
      onEnd(state.value, request.words)
    } catch (cause) {
      if (own.signal.aborted) return
      error.value = refusalOf(cause)
      state.value = stopPending(state.value)
    } finally {
      if (main === own) {
        main = null
        searching.value = false
      }
    }
  }

  async function follow(request: SearchRequest) {
    endFollow()
    const own: Following = { controller: new AbortController(), before: state.value, asked: new Set() }
    following = own
    const signal = own.controller.signal
    try {
      for await (const line of ask(request, signal)) {
        if (signal.aborted) return
        if (line.type === "plan") for (const cell of line.cells) own.asked.add(cell.key)
        state.value = reduceFollow(state.value, line)
      }
      onEnd(state.value, request.words)
    } catch (cause) {
      if (signal.aborted) return
      error.value = refusalOf(cause)
    } finally {
      // Ended here unless something else ended it first: a newer follow-up,
      // a new search, the person.
      if (following === own) endFollow()
    }
  }

  stopWithOwner(cancel)
  return { state, error, searching, search, follow, stop }
}
