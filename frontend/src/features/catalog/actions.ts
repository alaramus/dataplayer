import type { ActionInfo, ActionResult } from "@/client"
import { schemaToFields } from "@/shared/SchemaForm/jsonSchema"
import type { FieldSpec, JsonSchema } from "@/shared/SchemaForm/jsonSchema"

/**
 * One action, ready to be offered as a menu item.
 *
 * Nothing here is keyed by the name of an action: the label, whether it asks
 * for confirmation and what its form contains all come from the answer of the
 * server. A source that gains an action tomorrow needs no change on this side.
 */
export interface ActionCommand {
  name: string
  label: string
  destructive: boolean
  takesFile: boolean
  fields: FieldSpec[]
}

export function toCommands(actions: ActionInfo[]): ActionCommand[] {
  return actions.map((action) => ({
    name: action.name,
    label: action.title,
    destructive: action.destructive,
    takesFile: action.takes_file,
    fields: schemaToFields(action.params_schema as unknown as JsonSchema),
  }))
}

/** One node the action could not be done to, and what the server said. */
export interface ActionFailure {
  nodeId: string | null
  message: string
}

/** What became of one filled form applied to a set of nodes. */
export interface ActionOutcome {
  done: ActionResult[]
  failures: ActionFailure[]
  total: number
}

/**
 * The branches to re-read, each named once.
 *
 * Deleting five files out of one folder names that folder five times; reading
 * it five times would only produce the same answer four times over.
 */
export function reloadedBy(outcome: ActionOutcome): (string | null)[] {
  const seen = new Set<string | null>()
  for (const result of outcome.done) seen.add(result.reload_node_id ?? null)
  return [...seen]
}

/**
 * What to tell the user, in one line.
 *
 * A count only when there was more than one node: "Deleted 1 of 1" is a report
 * about a thing the user watched happen.
 */
export function summarize(outcome: ActionOutcome, label: string): string {
  const first = outcome.done[0]
  if (outcome.total === 1 && outcome.failures.length === 0) {
    return first?.message ?? `${label} done`
  }
  const head = `${label}: ${String(outcome.done.length)} of ${String(outcome.total)}`
  if (outcome.failures.length === 0) return head
  const said = outcome.failures
    .map((failure) => `${failure.nodeId ?? "?"} — ${failure.message}`)
    .join("; ")
  return `${head}. ${said}`
}
