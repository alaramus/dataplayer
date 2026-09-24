import { computed, shallowRef } from "vue"

import type { Tone } from "@/shared/ui/tokens"

/**
 * Everything the application has said, and what is on screen right now.
 *
 * A message is recorded first and shown second (D114): the card at the bottom
 * right is what the log does while the sheet is shut, not a separate thing
 * that happens to be worded the same.
 *
 * A module singleton rather than provide/inject or Pinia, for the reason
 * `realtime()` gives: in a browser tab the module and the application are the
 * same thing. It also keeps `useToast` callable from a component mounted on
 * its own in a unit test, which forty of them do.
 */

export interface NoticeAction {
  label: string
  run: () => void
}

export interface Notice {
  id: string
  /** Counted, not timed: two messages in one millisecond are still in order. */
  seq: number
  tone: Tone
  message: string
  at: number
  action: NoticeAction | null
}

/** How long any card stays on screen; its message remains in Activity. */
export const FADES_AFTER = 5000

/** How many cards are drawn at once. The rest are already in the sheet. */
export const CARDS = 3

/** How much of the log is kept. Older than this is not worth a scrollbar. */
const KEPT = 100

export function createNotices() {
  // shallowRef and whole-array replacement, as `shared/operations` does: an
  // entry carries a callback, and deep reactivity would walk into it.
  const entries = shallowRef<Notice[]>([])
  const onScreen = shallowRef<string[]>([])
  const doNotDisturb = shallowRef(false)
  const open = shallowRef(false)
  const seenSeq = shallowRef(0)
  let said = 0
  const timers = new Map<string, ReturnType<typeof setTimeout>>()

  function stopTimer(id: string) {
    const timer = timers.get(id)
    if (timer !== undefined) clearTimeout(timer)
    timers.delete(id)
  }

  /** Take a card off the screen. The message itself stays in the log. */
  function dismiss(id: string) {
    stopTimer(id)
    onScreen.value = onScreen.value.filter((shown) => shown !== id)
  }

  function record(notice: Omit<Notice, "id" | "at" | "seq">): string {
    const entry: Notice = { ...notice, id: crypto.randomUUID(), at: Date.now(), seq: ++said }
    entries.value = [entry, ...entries.value].slice(0, KEPT)
    // Nothing pops up over the sheet that is already showing it, and nothing
    // pops up at all while a person has asked not to be disturbed.
    if (!open.value && !doNotDisturb.value) {
      onScreen.value = [...onScreen.value, entry.id]
      timers.set(entry.id, setTimeout(() => { dismiss(entry.id) }, FADES_AFTER))
    }
    return entry.id
  }

  /** Remove a message from the log as well as from the screen. */
  function forget(id: string) {
    dismiss(id)
    entries.value = entries.value.filter((entry) => entry.id !== id)
  }

  function clear() {
    for (const id of timers.keys()) stopTimer(id)
    onScreen.value = []
    entries.value = []
  }

  function markSeen() {
    seenSeq.value = said
  }

  function setOpen(value: boolean) {
    open.value = value
    if (!value) return
    // Opening the sheet is being told; the cards would then be saying it
    // twice, over the thing that says it properly.
    for (const id of [...onScreen.value]) dismiss(id)
    markSeen()
  }

  const byId = computed(() => new Map(entries.value.map((entry) => [entry.id, entry])))

  /** The newest few, oldest first, so a new one appears nearest the button. */
  const cards = computed(() => onScreen.value
    .slice(-CARDS)
    .flatMap((id) => {
      const entry = byId.value.get(id)
      return entry === undefined ? [] : [entry]
    }))

  /** How many more are waiting in the sheet than the stack is showing. */
  const hidden = computed(() => Math.max(0, onScreen.value.length - CARDS))

  /** Recorded since the sheet was last looked at. */
  const unseen = computed(() => entries.value.filter((entry) => entry.seq > seenSeq.value).length)

  return {
    entries, cards, hidden, unseen, open, doNotDisturb,
    record, dismiss, forget, clear, markSeen, setOpen,
    setDoNotDisturb: (value: boolean) => { doNotDisturb.value = value },
  }
}

export type Notices = ReturnType<typeof createNotices>

let shared: Notices | null = null

export function notices(): Notices {
  shared ??= createNotices()
  return shared
}

/** Between tests, and on sign-out: what was said was said to somebody else. */
export function resetNotices() {
  shared?.clear()
  shared = null
}
