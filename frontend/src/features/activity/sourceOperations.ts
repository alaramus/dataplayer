import type { JobPublic } from "@/client"
import { sourceFeaturesKey } from "@/features/connectors/features"
import { t } from "@/shared/i18n"

/**
 * A source operation as its job records it (app/source_operations/models.py,
 * D123): the fixed targets and what became of each.
 *
 * Read out of the job's parameters, whose type the API leaves open. Every
 * field is checked, and a record that is not recognised is drawn as an
 * ordinary job rather than guessed at.
 */
export type TargetOutcome =
  | "pending" | "running" | "completed" | "already" | "refused" | "rolled_back" | "unknown"
export type ObservedState = "as_requested" | "unchanged" | "gone"

export interface OperationTargetRecord {
  schemaName: string
  name: string
  outcome: TargetOutcome
  message: string | null
  observed: ObservedState | null
}

export interface SourceOperationRecord {
  title: string
  summary: string
  targets: OperationTargetRecord[]
}

const OUTCOMES: ReadonlySet<string> = new Set<TargetOutcome>([
  "pending", "running", "completed", "already", "refused", "rolled_back", "unknown",
])
const OBSERVED: ReadonlySet<string> = new Set<ObservedState>(["as_requested", "unchanged", "gone"])
const SETTLED: ReadonlySet<TargetOutcome> = new Set<TargetOutcome>([
  "completed", "already", "refused", "rolled_back", "unknown",
])
const NEEDS_A_LOOK: ReadonlySet<TargetOutcome> = new Set<TargetOutcome>([
  "refused", "rolled_back", "unknown",
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function optionalText(value: unknown): value is string | null | undefined {
  return value === null || value === undefined || typeof value === "string"
}

function targetOf(value: unknown): OperationTargetRecord | null {
  if (!isRecord(value) || !isRecord(value.target)) return null
  const schemaName = value.target.schema_name
  const name = value.target.name
  const outcome = value.outcome
  const message = value.message
  const observed = value.observed
  if (typeof schemaName !== "string" || typeof name !== "string") return null
  if (typeof outcome !== "string" || !OUTCOMES.has(outcome)) return null
  if (!optionalText(message) || !optionalText(observed)) return null
  if (typeof observed === "string" && !OBSERVED.has(observed)) return null
  return {
    schemaName,
    name,
    outcome: outcome as TargetOutcome,
    message: message ?? null,
    observed: (observed ?? null) as ObservedState | null,
  }
}

export function sourceOperationOf(
  job: Pick<JobPublic, "kind" | "parameters">
): SourceOperationRecord | null {
  if (job.kind !== "source.operation" || !isRecord(job.parameters)) return null
  const title = job.parameters.title
  const summary = job.parameters.summary
  const targets = job.parameters.targets
  if (typeof title !== "string" || typeof summary !== "string" || !Array.isArray(targets)) {
    return null
  }
  const records = targets.map(targetOf)
  if (records.length === 0 || records.some((record) => record === null)) return null
  return { title, summary, targets: records as OperationTargetRecord[] }
}

/** How many targets have an outcome, of how many: counted, never estimated. */
export function settledCount(operation: SourceOperationRecord): number {
  return operation.targets.filter((target) => SETTLED.has(target.outcome)).length
}

function qualified(target: OperationTargetRecord): string {
  return `${target.schemaName}.${target.name}`
}

/**
 * The lines under a source operation: what it is working on while it runs,
 * and afterwards each target somebody has to look at, in the source's words.
 * The counts are in the job's own message, which the server wrote.
 */
export function operationLines(operation: SourceOperationRecord, active: boolean): string[] {
  if (active) {
    const running = operation.targets.find((target) => target.outcome === "running")
    return running === undefined ? [] : [t("activity.operations.now", { name: qualified(running) })]
  }
  return operation.targets
    .filter((target) => NEEDS_A_LOOK.has(target.outcome))
    .map((target) => {
      const said = target.message ?? target.outcome
      const seen = target.observed === null ? "" : ` (${t(`activity.operations.${target.observed}`)})`
      return `${qualified(target)}: ${said}${seen}`
    })
}

/**
 * Everything read through one connection that a source operation may have
 * changed. Rows and content are keyed by connection alone, so they go whole,
 * as they do after a structure change in the console.
 */
export function sourceDataKeys(connectorId: string): unknown[][] {
  return [
    [...sourceFeaturesKey(connectorId)],
    ["catalog", connectorId],
    ["nodePath", connectorId],
    ["actions", connectorId],
    ["nodeSummary", connectorId],
    ["relationModel", connectorId],
    ["rows", connectorId],
    ["content", connectorId],
    ["arrivingReferences", connectorId],
  ]
}

/**
 * The connections whose data moved since the last look, and what was seen.
 *
 * A job moves when a target settles or its state changes. Asked of the
 * polled listing, which is the authority, so a missed socket message still
 * ends in fresh data (D123).
 */
export function touchedSources(
  previous: ReadonlyMap<string, string>,
  jobs: JobPublic[]
): { seen: Map<string, string>; connectorIds: string[] } {
  const seen = new Map<string, string>()
  const touched = new Set<string>()
  for (const job of jobs) {
    const operation = sourceOperationOf(job)
    if (operation === null || job.subject_id === null) continue
    const signature = `${job.state}:${String(settledCount(operation))}`
    seen.set(job.id, signature)
    const before = previous.get(job.id)
    if (before !== undefined && before !== signature) touched.add(job.subject_id)
  }
  return { seen, connectorIds: [...touched] }
}
