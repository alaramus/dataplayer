import { ref } from "vue"

import type { JobPublic } from "@/client"
import { formatSize } from "@/features/catalog/nodes"
import { isWorking } from "@/features/services/jobs"

/**
 * A transfer between connections as its job records it
 * (app/connectors/paste/transfer.py, D168): what it carries, where, and what
 * became of each item.
 *
 * Read out of the job's parameters, whose type the API leaves open. Every
 * field is checked, and a record that is not recognised is drawn as an
 * ordinary job rather than guessed at. The words are the kind's own, so
 * nothing here names a kind.
 */
export type TransferOutcome = "pending" | "running" | "done" | "kept" | "failed" | "stopped"

export interface TransferItemRecord {
  name: string
  outcome: TransferOutcome
  message: string | null
  publishedAs: string | null
  rows: number | null
}

export interface TransferRecord {
  title: string
  doing: string
  done: string
  mode: "copy" | "move"
  sourceConnectorId: string
  sourceLabel: string
  destinationConnectorId: string
  destinationLabel: string
  items: TransferItemRecord[]
  bytesTotal: number | null
  bytesDone: number
  published: number
}

const OUTCOMES: ReadonlySet<string> = new Set<TransferOutcome>([
  "pending", "running", "done", "kept", "failed", "stopped",
])
/** What an item that did not arrive says when its own sentence is missing. */
const WORDS: Record<Exclude<TransferOutcome, "done">, string> = {
  pending: "not attempted",
  running: "interrupted",
  kept: "kept at its source",
  failed: "failed",
  stopped: "stopped",
}
/** The step a transfer shows while all the slots are taken (app/transfers/handler.py). */
const WAITING = "waiting for a free transfer slot"
/** Items listed under a finished transfer; the rest are counted. */
const LISTED = 10

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function itemOf(value: unknown): TransferItemRecord | null {
  if (!isRecord(value)) return null
  const name = text(value.name)
  const outcome = value.outcome
  if (name === null || typeof outcome !== "string" || !OUTCOMES.has(outcome)) return null
  return {
    name,
    outcome: outcome as TransferOutcome,
    message: text(value.message),
    publishedAs: text(value.published_as),
    rows: count(value.rows),
  }
}

export function transferOf(job: Pick<JobPublic, "kind" | "parameters">): TransferRecord | null {
  if (job.kind !== "paste.transfer" || !isRecord(job.parameters)) return null
  const at = job.parameters
  const fields = {
    title: text(at.title), doing: text(at.doing), done: text(at.done),
    sourceConnectorId: text(at.source_connector_id), sourceLabel: text(at.source_label),
    destinationConnectorId: text(at.destination_connector_id),
    destinationLabel: text(at.destination_label),
  }
  const bytesDone = count(at.bytes_done)
  const published = count(at.published)
  if (Object.values(fields).some((field) => field === null)) return null
  if (at.mode !== "copy" && at.mode !== "move") return null
  if (bytesDone === null || published === null || !Array.isArray(at.items)) return null
  const items = at.items.map(itemOf)
  if (items.length === 0 || items.some((item) => item === null)) return null
  return {
    ...(fields as { [key in keyof typeof fields]: string }),
    mode: at.mode,
    items: items as TransferItemRecord[],
    bytesTotal: count(at.bytes_total),
    bytesDone,
    published,
  }
}

/** Bytes measured so far, and of how many when that is known: never estimated. */
export function transferMeasure(transfer: TransferRecord): string {
  return transfer.bytesTotal === null
    ? `${formatSize(transfer.bytesDone)} written`
    : `${formatSize(transfer.bytesDone)} of ${formatSize(transfer.bytesTotal)}`
}

/** What the footer says of it: "Copying to SSH server · 45 MB of 120 MB". */
export function transferBrief(transfer: TransferRecord): string {
  return `${transfer.doing} to ${transfer.destinationLabel} · ${transferMeasure(transfer)}`
}

function itemLine(transfer: TransferRecord, item: TransferItemRecord): string {
  if (item.outcome === "done") {
    const renamed = item.publishedAs !== null && item.publishedAs !== item.name
    return `${item.name} — ${transfer.done}${renamed ? ` as ${item.publishedAs ?? ""}` : ""}`
  }
  return item.message ?? `${item.name} — ${WORDS[item.outcome]}`
}

/**
 * The lines under a transfer: the item in hand while it runs, and afterwards
 * the job's sentence and each item's outcome, the first ten and how many more.
 */
export function transferLines(job: JobPublic, transfer: TransferRecord): string[] {
  if (isWorking(job)) {
    if (job.step === WAITING) return ["Waiting for a free transfer slot"]
    const index = transfer.items.findIndex((item) => item.outcome === "running")
    const item = transfer.items[index]
    if (item === undefined) return [job.step ?? "Starting"]
    const total = transfer.items.length
    if (total > 1) return [`${item.name} — ${String(index + 1)} of ${String(total)}`]
    return [item.rows === null ? item.name : `${item.name} · ${String(item.rows)} rows`]
  }
  const lines = transfer.items.slice(0, LISTED).map((item) => itemLine(transfer, item))
  const more = transfer.items.length - LISTED
  return [
    ...(job.message === null ? [] : [job.message]),
    ...lines,
    ...(more > 0 ? [`and ${String(more)} more`] : []),
  ]
}

/** What Stop will do, said before it is pressed. */
export function transferStopHint(transfer: TransferRecord): string {
  return transfer.mode === "move"
    ? "Stops at once; files already moved stay moved."
    : "Stops at once; what already arrived stays."
}

/**
 * The transfers this tab started. Their endings are told here, as a Paste in
 * the request was (D113); another tab, or this one after a reload, finds them
 * in the sheet instead.
 */
export const startedHere = ref<ReadonlySet<string>>(new Set())

export function startedInThisTab(jobId: string) {
  startedHere.value = new Set([...startedHere.value, jobId])
}

export function toldInThisTab(jobId: string) {
  const next = new Set(startedHere.value)
  next.delete(jobId)
  startedHere.value = next
}

export interface TransferChanges {
  seen: Map<string, string>
  /** Connections whose catalogs should read again; `settled` when it ended. */
  touched: { connectorId: string; settled: boolean }[]
  /** Transfers this tab started that have just ended. */
  ended: JobPublic[]
}

/**
 * What the listing says moved since the last look.
 *
 * A transfer moves when a file arrives or it ends. A transfer this tab just
 * started counts as seen before its first listing, so one that ended before
 * the listing was read again still re-reads the catalogs and is told (D168).
 */
export function transferChanges(
  previous: ReadonlyMap<string, string>,
  jobs: JobPublic[],
  started: ReadonlySet<string>
): TransferChanges {
  const seen = new Map<string, string>()
  const touched: TransferChanges["touched"] = []
  const ended: JobPublic[] = []
  for (const job of jobs) {
    const transfer = transferOf(job)
    if (transfer === null) continue
    const signature = `${job.state}:${String(transfer.published)}`
    seen.set(job.id, signature)
    const before = previous.get(job.id) ?? (started.has(job.id) ? "started" : undefined)
    if (before === undefined || before === signature) continue
    const settled = !isWorking(job)
    touched.push({ connectorId: transfer.destinationConnectorId, settled })
    if (transfer.mode === "move") touched.push({ connectorId: transfer.sourceConnectorId, settled })
    if (settled && started.has(job.id)) ended.push(job)
  }
  return { seen, touched, ended }
}

/** How often a catalog re-reads while files keep arriving into it. */
export const REREAD_MS = 2000

/**
 * Re-reads a connection at most once every two seconds while a transfer runs,
 * never dropping the last arrival, and at once when it ends.
 */
export function createRereader(
  announce: (connectorId: string) => void,
  now: () => number = () => Date.now()
) {
  const lastRead = new Map<string, number>()
  const waiting = new Map<string, ReturnType<typeof setTimeout>>()

  function read(connectorId: string) {
    const timer = waiting.get(connectorId)
    if (timer !== undefined) clearTimeout(timer)
    waiting.delete(connectorId)
    lastRead.set(connectorId, now())
    announce(connectorId)
  }

  return {
    reread(connectorId: string, settled: boolean) {
      const since = now() - (lastRead.get(connectorId) ?? Number.NEGATIVE_INFINITY)
      if (settled || since >= REREAD_MS) {
        read(connectorId)
        return
      }
      if (waiting.has(connectorId)) return
      waiting.set(connectorId, setTimeout(() => { read(connectorId) }, REREAD_MS - since))
    },
    dispose() {
      for (const timer of waiting.values()) clearTimeout(timer)
      waiting.clear()
    },
  }
}
