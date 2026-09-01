import { AxiosError } from "axios"

import type { ServerError } from "@/shared/SchemaForm/useSchemaForm"

/**
 * What a failed request says, in the two shapes the backend answers with.
 *
 * An adapter failure arrives as `detail: {kind, message}`; a validation
 * failure arrives as `detail: [{loc, msg, type}]`; a refusal a route wrote out
 * itself arrives as `detail: "a sentence"`. Every screen used to carry its own
 * copy of this, and they had drifted: only the grid understood the second
 * shape. The third was read as unusable until the console started refusing
 * runs, where the whole point of the refusal is the reason it gives.
 *
 * The fallback is the caller's, because what could not be done differs by
 * screen: reading rows is not saving a connection.
 */
export function messageOf(cause: unknown, fallback: string): string {
  if (!(cause instanceof AxiosError)) return fallback

  const detail: unknown = cause.response?.data?.detail

  if (Array.isArray(detail)) {
    const first: unknown = detail[0]
    if (first && typeof first === "object" && "msg" in first) return String(first.msg)
    return fallback
  }

  if (detail && typeof detail === "object" && "message" in detail) {
    return String(detail.message)
  }

  // A string detail is written for the person reading it: "Writing is not
  // unlocked on this connection", not a code.
  if (typeof detail === "string" && detail.trim() !== "") return detail

  return fallback
}

/**
 * What the server answered with, or null when nothing arrived from it.
 *
 * The status is part of the answer and not only of the failure: a source
 * saying 501 to a capability is stating something about itself, and a request
 * that never arrived is stating nothing at all. Telling the two apart is the
 * difference between a row that is absent because it has no meaning and a row
 * that vanished because the network blinked.
 */
export function statusOf(cause: unknown): number | null {
  if (!(cause instanceof AxiosError)) return null
  return cause.response?.status ?? null
}

/**
 * The per-field errors of a rejected form, or null when the failure is not
 * about fields.
 *
 * The status is part of the question: a list under any other status is not a
 * field-level failure, and showing nothing would swallow the message.
 */
export function fieldErrorsFrom(cause: unknown): ServerError[] | null {
  if (!(cause instanceof AxiosError) || cause.response?.status !== 422) return null

  const detail: unknown = cause.response.data?.detail
  return Array.isArray(detail) ? (detail as ServerError[]) : null
}
