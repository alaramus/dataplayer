import type { LogEntry } from "@/client"
import type { Tone } from "@/shared/ui"

/**
 * One line of the server's log as the panel draws it (D184). Plain functions,
 * tested without mounting anything.
 */

/**
 * What an access line says the answer was. Uvicorn writes the request at INFO
 * whatever it came to, so a 500 would read as calm as a 200.
 */
export function statusOf(entry: LogEntry): number | null {
  if (entry.logger !== "uvicorn.access") return null
  const found = /" (\d{3})\s*$/.exec(entry.message)
  return found === null ? null : Number(found[1])
}

/** Red for what failed, amber for what warned or was refused, nothing else. */
export function toneOf(entry: LogEntry): Tone | null {
  if (entry.level === "ERROR" || entry.level === "CRITICAL") return "error"
  if (entry.level === "WARNING") return "warning"
  const status = statusOf(entry)
  if (status !== null && status >= 500) return "error"
  if (status !== null && status >= 400) return "warning"
  return null
}

/** The time of day to the millisecond, in the reader's own zone. */
export function timeOf(entry: LogEntry): string {
  const moment = new Date(entry.time)
  const pad = (value: number, size = 2) => String(value).padStart(size, "0")
  return `${pad(moment.getHours())}:${pad(moment.getMinutes())}:${pad(moment.getSeconds())}.${pad(moment.getMilliseconds(), 3)}`
}

/** Everything the entry holds, as text to paste into a message or a ticket. */
export function textOf(entry: LogEntry): string {
  const lines = [
    `${entry.time} ${entry.level} ${entry.process} ${entry.logger}`,
    ...(entry.request ? [`Request: ${entry.request}`] : []),
    ...(entry.ref ? [`Ref: ${entry.ref}`] : []),
    entry.message,
    ...(entry.exception ? [entry.exception] : []),
  ]
  return lines.join("\n")
}
