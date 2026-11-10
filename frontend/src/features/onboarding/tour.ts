/**
 * What a tour is made of, as plain data and functions over it (D355).
 *
 * A chapter rings one control at a time and is complete when what it asks has
 * happened. Nothing here touches the document: finding an element is handed
 * in, so the rules can be tested without a page.
 */

/** What one chapter learns and a later one needs. */
export interface TourMemory {
  /** The SQLite connection the first chapter made, and the file it opened. */
  database?: { id: string; name: string; folder: string; file: string }
  /** The connection to the person's own storage. */
  folder?: { id: string; name: string }
}

/** The first visible element a selector matches, or null. */
export type Finder = (selector: string) => Element | null

/** A selector, or null while the tour does not know enough to name one. */
export type Locate = (memory: TourMemory) => string | null

export interface TourTarget {
  locate: Locate
  /** What to do with the control, read in the language current when shown. */
  hint: (memory: TourMemory) => string
  /** A further condition than being on screen. */
  ready?: (memory: TourMemory, find: Finder) => boolean
}

/** A successful mutation, as the mutation cache tells it. */
export interface MutationSuccess {
  key: readonly unknown[] | undefined
  variables: unknown
  data: unknown
}

export type Completion =
  | {
      kind: "mutation"
      key: readonly string[]
      /** The memory to go on with when this success is the one asked for; null when it is not. */
      settle: (success: MutationSuccess, memory: TourMemory) => TourMemory | null
    }
  | { kind: "shown"; locate: Locate }

export interface TourChapter {
  id: string
  title: () => string
  /** In the order a person reaches them. */
  targets: readonly TourTarget[]
  done: Completion
}

/** A `data-testid` as a selector. Names come from the server, so quotes are escaped. */
export function testId(name: string): string {
  return `[data-testid="${name.replace(/["\\]/g, "\\$&")}"]`
}

export function testIdPrefix(prefix: string): string {
  return `[data-testid^="${prefix.replace(/["\\]/g, "\\$&")}"]`
}

/**
 * The target to ring: the furthest one on screen and ready.
 *
 * Furthest, so a chapter follows the person forward without being told; and
 * re-read every frame, so closing a window halfway moves the ring back.
 */
export function furthestTarget(chapter: TourChapter, memory: TourMemory, find: Finder): number {
  for (let index = chapter.targets.length - 1; index >= 0; index -= 1) {
    const target = chapter.targets[index]
    if (target === undefined) continue
    const selector = target.locate(memory)
    if (selector === null || find(selector) === null) continue
    if (target.ready !== undefined && !target.ready(memory, find)) continue
    return index
  }
  return -1
}

export function sameKey(a: readonly unknown[] | undefined, b: readonly unknown[]): boolean {
  return a !== undefined && a.length === b.length && a.every((part, index) => part === b[index])
}

/** The memory a mutation completes this chapter with, or null when it does not. */
export function settleMutation(
  chapter: TourChapter,
  success: MutationSuccess,
  memory: TourMemory
): TourMemory | null {
  const done = chapter.done
  if (done.kind !== "mutation" || !sameKey(success.key, done.key)) return null
  return done.settle(success, memory)
}

/** Whether a chapter completed by a control appearing has seen it. */
export function settledByShown(chapter: TourChapter, memory: TourMemory, find: Finder): boolean {
  const done = chapter.done
  if (done.kind !== "shown") return false
  const selector = done.locate(memory)
  return selector !== null && find(selector) !== null
}

/** A path inside the person's storage, as its folder and its file name. */
export function splitPath(path: string): { folder: string; file: string } {
  const parts = path.split("/").filter((part) => part !== "")
  const file = parts.pop() ?? ""
  return { folder: parts.join("/"), file }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}
