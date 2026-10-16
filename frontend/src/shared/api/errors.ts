import { AxiosError } from "axios"

import { problemMessage } from "@/shared/i18n"
import { isProblem } from "@/shared/i18n/problems"
import type { ServerError } from "@/shared/SchemaForm/useSchemaForm"

/**
 * What a failed request says, in the four shapes the backend answers with: a
 * coded refusal as `detail: {code, params, message}`, worded in the reader's
 * language (D225); an adapter failure as `detail: {kind, message}`; a
 * validation failure as `detail: [{loc, msg, type}]`; and a refusal a route
 * wrote itself as `detail: "a sentence"`. The last three are English until
 * their routes are coded.
 *
 * Every screen used to carry its own copy and they had drifted. The fallback
 * stays the caller's, because reading rows is not saving a connection.
 */
export function messageOf(cause: unknown, fallback: string): string {
  if (!(cause instanceof AxiosError)) return fallback

  const detail: unknown = cause.response?.data?.detail

  const coded = problemMessage(detail)
  if (coded !== null) return coded

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
 * The kind a source failure was reduced to, or null for any other failure:
 * an adapter failure's `error_kind`, or a coded refusal's (D225) — a source
 * lacking a capability is `config`.
 *
 * Read where a screen offers a way on rather than only a sentence: a key
 * that is `locked` is opened by its passphrase (D147), and a screen that
 * matched on the words of the message would break when they were reworded.
 */
export function errorKindOf(cause: unknown): string | null {
  if (!(cause instanceof AxiosError)) return null
  const detail: unknown = cause.response?.data?.detail
  if (isProblem(detail)) return detail.error_kind ?? null
  if (detail && typeof detail === "object" && "error_kind" in detail) {
    return typeof detail.error_kind === "string" ? detail.error_kind : null
  }
  return null
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
