import type { BestLine, CellLine, EndLine, PlanLine, SearchRequest } from "@/client"
import { router } from "@/router"
import { serverUrl } from "@/shared/servers/context"
import { useAuthStore } from "@/stores/auth"

/**
 * Reading the search's answer: JSON Lines over a POST (D201).
 *
 * Hand-written because the generated client reads a body whole, and the point
 * of the stream is to draw a group the moment its cell is in. The line types
 * are the generated ones, so a line the server changes changes them here.
 */
export type SearchLine = PlanLine | CellLine | BestLine | EndLine

/**
 * Every line type the server writes, and no other.
 *
 * A record over the generated union rather than a list: a type added on the
 * server fails to compile here until it is read, and a line of a type this
 * does not know is dropped rather than half understood.
 */
const LINE_TYPES: Record<SearchLine["type"], true> = {
  plan: true,
  cell: true,
  best: true,
  end: true,
}

export class SearchRefused extends Error {
  constructor(
    readonly status: number,
    message: string
  ) {
    super(message)
  }
}

export function parseLine(text: string): SearchLine | null {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    return null
  }
  if (typeof value !== "object" || value === null || !("type" in value)) return null
  const type = value.type
  if (typeof type !== "string" || !Object.hasOwn(LINE_TYPES, type)) return null
  return value as SearchLine
}

/** The lines of a body as they arrive, however the bytes were split. */
export async function* linesOf(body: ReadableStream<Uint8Array>): AsyncGenerator<SearchLine> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let end = buffer.indexOf("\n")
      while (end !== -1) {
        const parsed = parseLine(buffer.slice(0, end))
        buffer = buffer.slice(end + 1)
        if (parsed !== null) yield parsed
        end = buffer.indexOf("\n")
      }
    }
    buffer += decoder.decode()
    if (buffer.trim() !== "") {
      const parsed = parseLine(buffer)
      if (parsed !== null) yield parsed
    }
  } finally {
    reader.releaseLock()
  }
}

async function refusalOf(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = body.detail
      if (typeof detail === "string") return detail
    }
  } catch {
    // Not JSON: the status says enough.
  }
  return "The search could not be run"
}

/**
 * Ask the search, and read its answer line by line.
 *
 * Aborting the signal ends the request, which ends the answer on the server
 * as well (D200). A refused token signs the person out, as every other
 * request does.
 */
export async function* askSearch(
  request: SearchRequest,
  signal: AbortSignal
): AsyncGenerator<SearchLine> {
  const auth = useAuthStore()
  const response = await fetch(serverUrl("api/v1/search"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${auth.token ?? ""}`,
    },
    body: JSON.stringify(request),
    signal,
  })
  if (response.status === 401) {
    auth.clear()
    void router.push({ name: "login" })
    throw new SearchRefused(401, "Signed out")
  }
  if (!response.ok || response.body === null) {
    throw new SearchRefused(response.status, await refusalOf(response))
  }
  yield* linesOf(response.body)
}

/** Every line of one answer, for a caller that only wants the whole of it. */
export async function askWhole(
  request: SearchRequest,
  signal: AbortSignal
): Promise<SearchLine[]> {
  const lines: SearchLine[] = []
  for await (const line of askSearch(request, signal)) lines.push(line)
  return lines
}
