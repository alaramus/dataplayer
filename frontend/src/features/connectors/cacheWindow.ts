import type { SourceCacheWindows } from "@/client"
import { t } from "@/shared/i18n"
import type { SelectOption } from "@/shared/ui"

import { windowLabel } from "@/shared/freshness/freshness"

/**
 * How long this connection may keep an answer, as a form asks it.
 *
 * Three answers rather than two: leave it to the source, keep nothing, or
 * keep it for a while. The first is not a duration, so it travels as a word —
 * a select cannot hold null, and a zero standing for "the source decides"
 * would be the same value as "keep nothing" (D105).
 */
export const SOURCE_WINDOW = "source"

/**
 * What is offered. Ten seconds because that is what a source watching a queue
 * already chooses for itself, an hour at the top because a connection kept
 * longer than a working session is a copy rather than a cache.
 */
export const CACHE_WINDOWS = [0, 10, 30, 60, 300, 1800, 3600] as const

/**
 * What the source keeps its own answers for, when the server has said.
 *
 * Undefined while the list of source types is still loading, and null for a
 * source that keeps nothing at all — two different things, and the second is
 * the one where this field has nothing to do.
 */
export type SourceWindows = SourceCacheWindows | null | undefined

/** Whether choosing anything here would change anything. */
export function windowApplies(source: SourceWindows): boolean {
  return source !== null
}

/**
 * How the source's own choice reads.
 *
 * "As the source decides" says nothing to somebody who has never seen this
 * application's insides, so the numbers themselves are on the option: what
 * the default does is the whole reason to keep it (D105).
 */
export function sourceWindowLabel(source: SourceWindows): string {
  if (source === null) return t("connectors.cache.always_live")
  if (source === undefined) return t("connectors.cache.source_decides")
  return t("connectors.cache.source_decides_windows", {
    rows: windowLabel(source.fetch),
    lists: windowLabel(source.catalog),
  })
}

export function cacheWindowOptions(source: SourceWindows): SelectOption[] {
  return [
    { label: sourceWindowLabel(source), value: SOURCE_WINDOW },
    { label: t("connectors.cache.never"), value: 0 },
    ...CACHE_WINDOWS.filter((seconds) => seconds > 0).map((seconds) => ({
      label: t("connectors.cache.keep_for", { window: windowLabel(seconds) }),
      value: seconds,
    })),
  ]
}

/** The option that stands for what is stored. */
export function cacheWindowValue(seconds: number | null | undefined): string | number {
  return seconds === null || seconds === undefined ? SOURCE_WINDOW : seconds
}

/**
 * What a chosen option means, or nothing when it means nothing.
 *
 * Undefined rather than the source's answer for a value that is not offered:
 * a select that reported something unreadable would silently hand the window
 * back to the source, and the caller would save that.
 */
export function cacheWindowOf(value: unknown): number | null | undefined {
  if (value === SOURCE_WINDOW) return null
  const chosen = CACHE_WINDOWS.find((seconds) => seconds === value)
  return chosen
}

/** The line under the field: what this choice does, in one sentence. */
export function cacheWindowNote(seconds: number | null, source: SourceWindows): string {
  if (source === null) {
    return t("connectors.cache.note_keeps_nothing")
  }
  if (seconds === null) {
    return source === undefined
      ? t("connectors.cache.note_source_says")
      : t("connectors.cache.note_source", {
          rows: windowLabel(source.fetch),
          lists: windowLabel(source.catalog),
        })
  }
  if (seconds <= 0) return t("connectors.cache.note_every_read")
  return t("connectors.cache.note_after", { window: windowLabel(seconds) })
}
