/**
 * Whether what is on screen was read now or kept, and how old it is.
 *
 * Two caches sit between a source and a grid: the browser's, which decides
 * whether to ask at all, and the server's, which decides whether to read.
 * Neither can answer the question on its own — the browser knows when the
 * reply arrived, the server knows how long the reply had been sitting there
 * first — so the server sends its part and this adds the browser's (D105).
 *
 * Plain functions, so what a badge says can be tested without mounting one.
 */

/** What the server did with the read, as `X-Data-Cache` reports it. */
export type CacheOutcome = "hit" | "miss" | "coalesced" | "refreshed" | "bypass"

export interface Freshness {
  outcome: CacheOutcome
  /** When the source was actually read, in epoch milliseconds. */
  readAt: number
}

const OUTCOMES: CacheOutcome[] = ["hit", "miss", "coalesced", "refreshed", "bypass"]

/**
 * What a response says about itself.
 *
 * A reply without the headers is treated as a read of the source, because
 * that is what a route that does not cache is: `bypass` is the answer the
 * server itself gives for a source with no freshness rules.
 */
export function freshnessOf(
  headers: Record<string, unknown> | undefined,
  now: number = Date.now()
): Freshness {
  const outcome = String(headers?.["x-data-cache"] ?? "")
  const age = Number(headers?.["x-data-cache-age"] ?? 0)
  const found = OUTCOMES.find((known) => known === outcome)
  return {
    outcome: found ?? "bypass",
    // Rounded away from a future timestamp: a clock that says the source was
    // read after this reply arrived would show a negative age.
    readAt: now - (Number.isFinite(age) && age > 0 ? age * 1000 : 0),
  }
}

/** Whether this answer is the read itself rather than something kept. */
export function isLive(freshness: Freshness, now: number = Date.now()): boolean {
  return freshness.outcome !== "hit" && now - freshness.readAt < 1000
}

/** How long ago, in the shortest words that are still true. */
export function ageLabel(milliseconds: number): string {
  const seconds = Math.max(Math.round(milliseconds / 1000), 0)
  if (seconds < 60) return `${String(seconds)}s`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${String(minutes)}m`
  const hours = Math.round(minutes / 60)
  return hours < 24 ? `${String(hours)}h` : `${String(Math.round(hours / 24))}d`
}

/**
 * What the badge says.
 *
 * `Live` only while the reply is the read and nothing has aged since. A page
 * read from the source four minutes ago is not live any more, whatever the
 * server said when it sent it — which is the case that made somebody press
 * reload out of doubt.
 */
export function freshnessLabel(
  freshness: Freshness,
  now: number = Date.now()
): string {
  return isLive(freshness, now) ? "Live" : ageLabel(now - freshness.readAt)
}

/** How long this connection keeps an answer, in the same short words. */
export function windowLabel(seconds: number): string {
  if (seconds <= 0) return "nothing"
  return ageLabel(seconds * 1000)
}

/**
 * The whole sentence, for somebody who stopped to ask.
 *
 * `cacheTtlSeconds` is what the connection was told to keep, `null` when its
 * owner left that to the source — in which case the window is not this
 * screen's to state.
 */
export function freshnessTooltip(
  freshness: Freshness,
  cacheTtlSeconds: number | null | undefined,
  now: number = Date.now()
): string {
  const read =
    isLive(freshness, now)
      ? "Read from the source just now."
      : `Read from the source ${ageLabel(now - freshness.readAt)} ago.`
  const kept =
    cacheTtlSeconds === null || cacheTtlSeconds === undefined
      ? "This connection keeps answers for as long as the source says."
      : cacheTtlSeconds <= 0
        ? "This connection keeps nothing: every read reaches the source."
        : `This connection keeps answers for ${windowLabel(cacheTtlSeconds)}.`
  return `${read} ${kept} Press to read it again.`
}
