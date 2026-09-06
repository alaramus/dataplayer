import { statusOf } from "@/shared/api/errors"

/**
 * Whether a failed request is worth making again.
 *
 * vue-query retries everything three times, which is right for a request that
 * never arrived and wrong for one the server read and refused: it will be
 * refused again, and the retries only hold a spinner on screen first. Opening
 * a `.dump` in a file source took five seconds to say it is binary.
 *
 * The line is the status class, with the two 4xx codes that are about the
 * moment as exceptions.
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
