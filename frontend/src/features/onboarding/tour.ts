import { t } from "@/shared/i18n"
import type { MessageKey } from "@/shared/i18n"

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
  /** The pipeline a short tour made, taken away with it. */
  pipeline?: { id: string }
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
  /** In a chapter only shown, ringed here is far enough for Next. */
  enough?: boolean
  /**
   * In a chapter only shown, pressing the control completes it: what it opens
   * covers the chapter's own targets, and the hint would fall back to the first.
   */
  pressCompletes?: boolean
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
  /** A control on screen; with `atLeast`, that many of them. */
  | { kind: "shown"; locate: Locate; atLeast?: number }
  /** Shown rather than done: the hint's own button, once the last target is ringed. */
  | { kind: "next" }

export interface TourChapter {
  id: string
  title: () => string
  /** In the order a person reaches them. */
  targets: readonly TourTarget[]
  done: Completion
}

/** The few requests a tour makes itself, before and after the person's part. */
export interface TourKit {
  /** A SQLite file with the lab, and its connection (D263). */
  makePractice: () => Promise<{ id: string; name: string; path: string }>
  /** The person's connection to their own storage, made when there is none. */
  ensureFolder: () => Promise<{ id: string; name: string }>
  /** A connection deleted with the file it holds (D356). */
  removeWithFile: (connectorId: string) => Promise<void>
  removePipeline: (pipelineId: string) => Promise<void>
}

export interface TourDefinition {
  /** `basics` is the welcome's tour; the rest are the short ones (D356). */
  id: "basics" | "views" | "pipeline" | "dashboards" | "agent"
  title: () => string
  /** One sentence in the list of tours. */
  summary: () => string
  chapters: readonly TourChapter[]
  /** What the tour makes before the first chapter, remembered for the rest. */
  setup?: (kit: TourKit) => Promise<TourMemory>
  /** What it takes away when it ends, finished or not. */
  cleanup?: (kit: TourKit, memory: TourMemory) => Promise<void>
  /** A closing card after the last chapter; without one the tour ends there. */
  closing?: { title: () => string; text: () => string }
  /** Its last chapter offers the list of tours in Preferences beside Finish. */
  moreTours?: boolean
}

/**
 * Whether the hint offers its button: a chapter only shown, with its last
 * target ringed — or none of them on screen, where waiting would wait for ever.
 */
export function offersNext(chapter: TourChapter, ringed: number): boolean {
  if (chapter.done.kind !== "next") return false
  return ringed === -1 || ringed === chapter.targets.length - 1 || chapter.targets[ringed]?.enough === true
}

/** A hint read in the language current when it is shown. */
export const say = (key: MessageKey, params?: Record<string, string>) => () => t(key, params)

/** The SQLite connection a tour made, as the memory keeps it. */
export function rememberDatabase(
  memory: TourMemory,
  made: { id: string; name: string; path: string }
): TourMemory {
  return { ...memory, database: { id: made.id, name: made.name, ...splitPath(made.path) } }
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

/** How many laid-out elements a selector matches. */
export type Counter = (selector: string) => number

/** Whether a chapter completed by a control appearing has seen it. */
export function settledByShown(
  chapter: TourChapter,
  memory: TourMemory,
  find: Finder,
  count: Counter = (selector) => (find(selector) === null ? 0 : 1)
): boolean {
  const done = chapter.done
  if (done.kind !== "shown") return false
  const selector = done.locate(memory)
  if (selector === null || find(selector) === null) return false
  return done.atLeast === undefined || count(selector) >= done.atLeast
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
