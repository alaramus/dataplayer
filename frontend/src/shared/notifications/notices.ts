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
  /** What it is about, where a message alone would not say: a job's name. */
  title?: string
  message: string
  /** The steps behind it, one to a line: each link of a pipeline's run. */
  lines?: string[]
  at: number
  action: NoticeAction | null
}

/**
 * A card with no record of its own, because its record is elsewhere: a thing
 * that needs somebody is recorded in the first section of the sheet, and the
 * card is only the moment it arrived (D181).
 */
export type Announcement = Pick<Notice, "id" | "tone" | "title" | "message" | "action">

/** How long any card stays on screen; its message remains in Activity. */
export const FADES_AFTER = 5000

/** Longer for what went wrong: missing it is the costlier of the two. */
export const ERROR_FADES_AFTER = 10000

/** How many cards are drawn at once. The rest are already in the sheet. */
export const CARDS = 3

/** How much of the log is kept. Older than this is not worth a scrollbar. */
const KEPT = 100

export function createNotices() {
  // shallowRef and whole-array replacement, as `shared/operations` does: an
  // entry carries a callback, and deep reactivity would walk into it.
  const entries = shallowRef<Notice[]>([])
  const announced = shallowRef(new Map<string, Announcement>())
  /** Taken out of the log by hand, so a record under the same id stays out. */
  const forgotten = shallowRef<ReadonlySet<string>>(new Set())
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
    if (announced.value.has(id)) {
      const next = new Map(announced.value)
      next.delete(id)
      announced.value = next
    }
  }

  /**
   * Put a card up — unless the sheet already shows what it says, or a person
   * has asked not to be disturbed. Whether it went up is the answer.
   */
  function show(id: string, tone: Tone): boolean {
    if (open.value || doNotDisturb.value) return false
    onScreen.value = [...onScreen.value.filter((shown) => shown !== id), id]
    stopTimer(id)
    timers.set(id, setTimeout(() => { dismiss(id) }, tone === "error" ? ERROR_FADES_AFTER : FADES_AFTER))
    return true
  }

  /**
   * Write a message into the log, and put its card up.
   *
   * `id` names something that must be recorded once however often it is
   * seen — a job, read again at every poll — and a message forgotten by hand
   * under that id is not recorded again. `at` places one that happened before
   * it was seen, such as a job that ended before a reload, by when it happened.
   * `card: false` records without interrupting.
   */
  function record(
    notice: Omit<Notice, "id" | "at" | "seq">,
    options: { id?: string; at?: number; card?: boolean } = {}
  ): string {
    const id = options.id ?? crypto.randomUUID()
    if (forgotten.value.has(id) || entries.value.some((entry) => entry.id === id)) return id
    const entry: Notice = { ...notice, id, at: options.at ?? Date.now(), seq: ++said }
    // Newest first by when it happened, not by when it was written down.
    entries.value = [...entries.value, entry]
      .sort((a, b) => b.at - a.at || b.seq - a.seq)
      .slice(0, KEPT)
    if (options.card !== false) show(id, notice.tone)
    return id
  }

  /** A card whose record is kept elsewhere; see `Announcement`. */
  function announce(card: Announcement) {
    const next = new Map(announced.value)
    next.set(card.id, card)
    announced.value = next
    if (!show(card.id, card.tone)) dismiss(card.id)
  }

  /** Remove a message from the log as well as from the screen. */
  function forget(id: string) {
    dismiss(id)
    entries.value = entries.value.filter((entry) => entry.id !== id)
    forgotten.value = new Set([...forgotten.value, id])
  }

  /** Forget everything said, as each would be forgotten one at a time. */
  function forgetAll() {
    for (const entry of entries.value) forget(entry.id)
  }

  /** Between accounts: nothing said, and nothing kept out either. */
  function clear() {
    for (const id of timers.keys()) stopTimer(id)
    onScreen.value = []
    entries.value = []
    announced.value = new Map()
    forgotten.value = new Set()
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

  const byId = computed(() => new Map<string, Announcement>([
    ...entries.value.map((entry) => [entry.id, entry] as const),
    ...announced.value,
  ]))

  /** The newest few, oldest first, so a new one appears nearest the button. */
  const cards = computed(() => onScreen.value
    .slice(-CARDS)
    .flatMap((id) => {
      const card = byId.value.get(id)
      return card === undefined ? [] : [card]
    }))

  /** How many more are waiting in the sheet than the stack is showing. */
  const hidden = computed(() => Math.max(0, onScreen.value.length - CARDS))

  /** Recorded since the sheet was last looked at. */
  const unseen = computed(() => entries.value.filter((entry) => entry.seq > seenSeq.value).length)

  return {
    entries, cards, hidden, unseen, open, doNotDisturb, forgotten,
    record, announce, dismiss, forget, forgetAll, clear, markSeen, setOpen,
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
