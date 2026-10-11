import type { ProblemDetail } from "@/client"

/** Every code the server refuses with; the set is the server's (D225). */
export type ProblemCode = ProblemDetail["code"]

/** Whatever the server put under `detail`, read as a coded refusal or not. */
export function isProblem(detail: unknown): detail is ProblemDetail {
  return (
    !!detail &&
    typeof detail === "object" &&
    "code" in detail &&
    typeof detail.code === "string" &&
    "message" in detail &&
    typeof detail.message === "string"
  )
}

/**
 * A refusal in the reader's language: the server's English as it is, or the
 * dictionary's sentence with its `{name}` parameters filled in. A code the
 * dictionary lacks — a newer server than this build — falls back to English
 * rather than to a blank.
 */
export function wordProblem(
  detail: ProblemDetail,
  dictionary: Partial<Record<ProblemCode, string>> | null
): string {
  const template = dictionary?.[detail.code]
  if (template === undefined) return detail.message
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in detail.params ? String(detail.params[name]) : whole
  )
}
