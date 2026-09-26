import type { JobPublic } from "@/client"
import { isWorking } from "@/features/services/jobs"

import { isRecord, listed, text, transferLines, transferOf, WAITING } from "./transfers"
import type { TransferRecord, Writing } from "./transfers"

/**
 * A pipeline's run as its job records it (app/pipelines/record.py, D177): the
 * links it carries out in order, and what became of each.
 *
 * Read out of the job's parameters field by field, as a transfer is; a record
 * that is not recognised is drawn as an ordinary job rather than guessed at.
 */
export type StepOutcome = "waiting" | "running" | "done" | "failed" | "not_run"

export interface RunStepRecord {
  linkId: string
  title: string
  sourceLabel: string
  targetLabel: string
  sourceConnectorId: string
  destinationConnectorId: string
  changesSource: boolean
  outcome: StepOutcome
  message: string | null
  /** A transfer step's own payload, once it is planned. */
  transfer: TransferRecord | null
  /** The link whose result it reads (D178), and the name it made its own under. */
  reads: string | null
  madeName: string | null
}

export interface PipelineRunRecord {
  pipelineName: string
  steps: RunStepRecord[]
}

const OUTCOMES: ReadonlySet<string> = new Set<StepOutcome>(["waiting", "running", "done", "failed", "not_run"])

function stepOf(value: unknown): RunStepRecord | null {
  if (!isRecord(value) || !isRecord(value.paste)) return null
  const fields = {
    linkId: text(value.link_id),
    title: text(value.title),
    sourceLabel: text(value.source_label),
    targetLabel: text(value.target_label),
    sourceConnectorId: text(value.paste.source_connector_id),
    destinationConnectorId: text(value.destination_connector_id),
  }
  const outcome = value.outcome
  if (Object.values(fields).some((field) => field === null)) return null
  if (typeof outcome !== "string" || !OUTCOMES.has(outcome) || typeof value.changes_source !== "boolean") return null
  return {
    ...(fields as { [key in keyof typeof fields]: string }),
    changesSource: value.changes_source,
    outcome: outcome as StepOutcome,
    message: text(value.message),
    transfer: isRecord(value.transfer) ? transferOf({ kind: "paste.transfer", parameters: value.transfer }) : null,
    reads: text(value.reads),
    madeName: text(value.made_name),
  }
}

export function pipelineRunOf(job: Pick<JobPublic, "kind" | "parameters">): PipelineRunRecord | null {
  if (job.kind !== "pipeline.run" || !isRecord(job.parameters)) return null
  const name = text(job.parameters.pipeline_name)
  const steps = Array.isArray(job.parameters.steps) ? job.parameters.steps.map(stepOf) : []
  if (name === null || steps.length === 0 || steps.some((step) => step === null)) return null
  return { pipelineName: name, steps: steps as RunStepRecord[] }
}

/** The step being carried out, and where it is: "2 of 5". */
function current(run: PipelineRunRecord): { step: RunStepRecord; at: string } | null {
  const index = run.steps.findIndex((step) => step.outcome === "running")
  const step = run.steps[index]
  return step === undefined ? null : { step, at: `${String(index + 1)} of ${String(run.steps.length)}` }
}

/** What the footer says of it: "Nightly · 2 of 5: Save as CSV". */
export function pipelineBrief(run: PipelineRunRecord): string {
  const now = current(run)
  return now === null ? `${run.pipelineName} · starting` : `${run.pipelineName} · ${now.at}: ${now.step.title}`
}

/** Links that have ended, done or not. */
export function settledSteps(run: PipelineRunRecord): number {
  return run.steps.filter((step) => step.outcome === "done" || step.outcome === "failed").length
}

/** How a step ended, where a finished run lists it. */
function ending(step: RunStepRecord): string {
  switch (step.outcome) {
    case "done": return step.message ?? "done"
    case "failed": return step.message ?? "failed"
    // The server stopped under it: nothing settled it.
    case "running": return "interrupted"
    case "waiting":
    case "not_run": return "not run"
  }
}

/**
 * The lines under a run: the link in hand and its file while it runs, and
 * afterwards the run's sentence and one line for each link — the first ten.
 */
export function pipelineLines(job: JobPublic, run: PipelineRunRecord): string[] {
  if (isWorking(job)) {
    const now = current(run)
    if (now === null) return ["Starting"]
    const head = `${now.at}: ${now.step.title} — ${now.step.sourceLabel} → ${now.step.targetLabel}`
    if (job.step === WAITING) return [head, "Waiting for a free transfer slot"]
    const transfer = now.step.transfer
    return transfer === null || transfer.current === null ? [head] : [head, ...transferLines(job, transfer)]
  }
  return [
    ...(job.message === null ? [] : [job.message]),
    ...listed(run.steps.map((step, index) => `${String(index + 1)}. ${step.title} — ${ending(step)}${read(run, step)}`), 0),
  ]
}

/** What a link that ran read of another's result, by the name it was made under. */
function read(run: PipelineRunRecord, step: RunStepRecord): string {
  if (step.reads === null || (step.outcome !== "done" && step.outcome !== "failed")) return ""
  const maker = run.steps.find((one) => one.linkId === step.reads)
  return maker?.madeName ? ` · read ${maker.madeName}` : ""
}

/** The connections a run has written into, re-read as its links end (D177). */
export function pipelineWriting(job: JobPublic): Writing | null {
  const run = pipelineRunOf(job)
  if (run === null) return null
  const started = run.steps.filter((step) => step.outcome !== "waiting" && step.outcome !== "not_run")
  const moving = current(run)?.step.transfer?.published ?? 0
  return {
    signature: `${job.state}:${String(settledSteps(run))}:${String(moving)}`,
    connectorIds: [...new Set(started.flatMap((step) => [
      step.destinationConnectorId,
      ...(step.changesSource ? [step.sourceConnectorId] : []),
    ]))],
  }
}
