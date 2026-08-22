import { AxiosError } from "axios"

import type { ServerError } from "@/shared/SchemaForm/useSchemaForm"

/**
 * What a failed request says, in the two shapes the backend answers with.
 *
 * An adapter failure arrives as `detail: {kind, message}`; a validation
 * failure arrives as `detail: [{loc, msg, type}]`. Every screen used to carry
 * its own copy of this, and they had drifted: only the grid understood the
 * second shape.
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

  return fallback
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
