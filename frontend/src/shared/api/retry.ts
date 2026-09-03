import { statusOf } from "@/shared/api/errors"

/**
 * Whether a failed request is worth making again.
 *
 * vue-query's default is to retry everything three times with a growing gap,
 * which is right for the failure it was written for: a request that never
 * arrived, or a server that was briefly not there. It is wrong for the other
 * kind. When the server read the request and refused it — this file is binary,
 * this source has no such capability, you may not do that here — the same
 * request will be refused again, and retrying it only holds a spinner on
 * screen for several seconds before showing the answer that arrived at once.
 *
 * That is not hypothetical: opening a `.dump` in a file source waited about
 * five seconds to say that it is binary, and every second of it was this.
 *
 * The line is the status class. 4xx is the server saying something about the
 * request, and it will say it again; 5xx and a request with no response at all
 * are about the moment, and a moment passes. The two exceptions are the two
 * 4xx codes that are also about the moment.
 */

/** Refusals that are about right now rather than about the request. */
const WORTH_ASKING_AGAIN = new Set([
  408, // Request Timeout
  429, // Too Many Requests
])

export function isSettledRefusal(error: unknown): boolean {
  const status = statusOf(error)
  if (status === null) return false
  return status >= 400 && status < 500 && !WORTH_ASKING_AGAIN.has(status)
}

/**
 * The retry rule for every query in the application.
 *
 * A pure function of the two things vue-query knows, so the rule can be read
 * and tested without a query client.
 */
export function shouldRetry(failureCount: number, error: unknown, ceiling: number): boolean {
  if (isSettledRefusal(error)) return false
  return failureCount < ceiling
}
