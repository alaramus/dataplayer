import { ref } from "vue"

import type { JobPublic } from "@/client"
import { formatSize } from "@/features/catalog/nodes"
import { isWorking } from "@/features/services/jobs"

/**
 * A transfer between connections as its job records it
 * (app/connectors/paste/transfer.py, D168, D169): what was ticked, with the
 * files it held and what became of them, and the files that did not arrive.
 *
 * Read out of the job's parameters, whose type the API leaves open. Every
 * field is checked, and a record that is not recognised is drawn as an
 * ordinary job rather than guessed at. The words are the kind's own, so
 * nothing here names a kind.
 */
export type TransferOutcome = "pending" | "running" | "done" | "kept" | "failed" | "stopped"

export interface TransferItemRecord {
  name: string
  isFolder: boolean
  outcome: TransferOutcome
  message: string | null
  publishedAs: string | null
  rows: number | null
  files: number
  arrived: number
  failed: number
  skipped: number
  removed: number
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
  filesDone: number
  current: string | null
  problems: string[]
  problemsMore: number
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
/** The steps a transfer shows besides its work (app/transfers/handler.py). */
export const WAITING = "waiting for a free transfer slot"
const REMOVING = "removing the sources"
/** Items, and files that did not arrive, listed under a finished transfer. */
const LISTED = 10

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

export function text(value: unknown): string | null {
  return typeof value === "string" ? value : null
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

/** Counts as a person reads them: "4,211". */
function counted(value: number): string {
  return value.toLocaleString("en-US")
}

function itemOf(value: unknown): TransferItemRecord | null {
  if (!isRecord(value)) return null
  const name = text(value.name)
  const outcome = value.outcome
  const numbers = [value.files, value.arrived, value.failed, value.skipped, value.removed].map(count)
  if (name === null || typeof outcome !== "string" || !OUTCOMES.has(outcome)) return null
  if (typeof value.is_folder !== "boolean" || numbers.some((number) => number === null)) return null
  const [files, arrived, failed, skipped, removed] = numbers as number[]
  return {
    name,
    isFolder: value.is_folder,
    outcome: outcome as TransferOutcome,
    message: text(value.message),
    publishedAs: text(value.published_as),
    rows: count(value.rows),
    files: files ?? 0,
    arrived: arrived ?? 0,
    failed: failed ?? 0,
    skipped: skipped ?? 0,
    removed: removed ?? 0,
  }
}

function problemOf(value: unknown): string | null {
  return isRecord(value) ? text(value.message) : null
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
  const numbers = {
    bytesDone: count(at.bytes_done), published: count(at.published),
    filesDone: count(at.files_done), problemsMore: count(at.problems_more),
  }
  if (Object.values(fields).some((field) => field === null)) return null
  if (Object.values(numbers).some((number) => number === null)) return null
  if (at.mode !== "copy" && at.mode !== "move") return null
  if (!Array.isArray(at.items) || !Array.isArray(at.problems)) return null
  const items = at.items.map(itemOf)
  const problems = at.problems.map(problemOf)
  if (items.length === 0 || items.some((item) => item === null)) return null
  if (problems.some((problem) => problem === null)) return null
  return {
    ...(fields as { [key in keyof typeof fields]: string }),
    ...(numbers as { [key in keyof typeof numbers]: number }),
    mode: at.mode,
    items: items as TransferItemRecord[],
    bytesTotal: count(at.bytes_total),
    current: text(at.current),
    problems: problems as string[],
  }
}

/** Bytes measured so far, and of how many when that is known: never estimated. */
export function transferMeasure(transfer: TransferRecord): string {
  return transfer.bytesTotal === null
    ? `${formatSize(transfer.bytesDone)} written`
    : `${formatSize(Math.min(transfer.bytesDone, transfer.bytesTotal))} of ${formatSize(transfer.bytesTotal)}`
}

/** What the footer says of it: "Copying to SSH server · 45 MB of 120 MB". */
export function transferBrief(transfer: TransferRecord): string {
  return `${transfer.doing} to ${transfer.destinationLabel} · ${transferMeasure(transfer)}`
}

function filesTotal(transfer: TransferRecord): number {
  return transfer.items.reduce((total, item) => total + item.files, 0)
}

/** A ticked folder: how many of its files arrived, and what became of the rest. */
function folderLine(transfer: TransferRecord, item: TransferItemRecord): string {
  const moving = transfer.mode === "move"
  const arrived = moving ? item.removed : item.arrived
  const kept = moving ? item.arrived - item.removed : 0
  const parts = [
    `${counted(arrived)} ${transfer.done}`,
    ...(kept > 0 ? [`${counted(kept)} kept at the source`] : []),
    ...(item.failed > 0 ? [`${counted(item.failed)} failed`] : []),
    ...(item.skipped > 0 ? [`${counted(item.skipped)} skipped`] : []),
  ]
  const renamed = item.publishedAs !== null && item.publishedAs !== item.name
  return `${item.name}${renamed ? ` as ${item.publishedAs ?? ""}` : ""} — ${parts.join(", ")}`
}

function itemLine(transfer: TransferRecord, item: TransferItemRecord): string {
  if (item.outcome === "pending" || item.outcome === "running") {
    return `${item.name} — ${WORDS[item.outcome]}`
  }
  if (item.isFolder && item.outcome !== "stopped") return folderLine(transfer, item)
  if (item.outcome === "done") {
    const renamed = item.publishedAs !== null && item.publishedAs !== item.name
    return `${item.name} — ${transfer.done}${renamed ? ` as ${item.publishedAs ?? ""}` : ""}`
  }
  return item.message ?? `${item.name} — ${WORDS[item.outcome]}`
}

export function listed(lines: string[], more: number): string[] {
  const rest = lines.length - LISTED + more
  return [...lines.slice(0, LISTED), ...(rest > 0 ? [`and ${counted(rest)} more`] : [])]
}

/**
 * The lines under a transfer: the file in hand while it runs, and afterwards
 * the job's sentence, one line for each ticked item and each file that did
 * not arrive — the first ten of each and how many more.
 */
export function transferLines(job: JobPublic, transfer: TransferRecord): string[] {
  if (isWorking(job)) {
    if (job.step === WAITING) return ["Waiting for a free transfer slot"]
    if (job.step === REMOVING) return ["Removing the sources"]
    const current = transfer.current
    if (current === null) return [job.step ?? "Starting"]
    const total = filesTotal(transfer)
    if (total > 1) {
      const at = Math.min(transfer.filesDone + 1, total)
      return [`${current} — ${counted(at)} of ${counted(total)}`]
    }
    const rows = transfer.items[0]?.rows ?? null
    return [rows === null ? current : `${current} · ${counted(rows)} rows`]
  }
  return [
    ...(job.message === null ? [] : [job.message]),
    ...listed(transfer.items.map((item) => itemLine(transfer, item)), 0),
    ...listed(transfer.problems, transfer.problemsMore),
  ]
}

/** What Stop will do, said before it is pressed. */
export function transferStopHint(transfer: TransferRecord): string {
  return transfer.mode === "move"
    ? "Stops at once; the sources stay until everything has arrived."
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
 * What a job writing into connections says of itself: a signature that
 * changes as things arrive, and the connections it writes into.
 */
export interface Writing {
  signature: string
  connectorIds: string[]
}

export function transferWriting(job: JobPublic): Writing | null {
  const transfer = transferOf(job)
  if (transfer === null) return null
  return {
    signature: `${job.state}:${String(transfer.published)}`,
    connectorIds: [
      transfer.destinationConnectorId,
      ...(transfer.mode === "move" ? [transfer.sourceConnectorId] : []),
    ],
  }
}

/**
 * What the listing says moved since the last look.
 *
 * A transfer moves when a file arrives or it ends. A transfer this tab just
 * started counts as seen before its first listing, so one that ended before
 * the listing was read again still re-reads the catalogs and is told (D168).
 * `writingOf` reads other jobs that write the same way: a pipeline's run
 * (D177).
 */
export function transferChanges(
  previous: ReadonlyMap<string, string>,
  jobs: JobPublic[],
  started: ReadonlySet<string>,
  writingOf: (job: JobPublic) => Writing | null = transferWriting
): TransferChanges {
  const seen = new Map<string, string>()
  const touched: TransferChanges["touched"] = []
  const ended: JobPublic[] = []
  for (const job of jobs) {
    const writing = writingOf(job)
    if (writing === null) continue
    seen.set(job.id, writing.signature)
    const before = previous.get(job.id) ?? (started.has(job.id) ? "started" : undefined)
    if (before === undefined || before === writing.signature) continue
    const settled = !isWorking(job)
    for (const connectorId of writing.connectorIds) touched.push({ connectorId, settled })
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
