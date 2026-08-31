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
  /** Whether the source can say what this would do before it is done. */
  previews: boolean
  /** Whether the action returns one native browser download for all targets. */
  downloads: boolean
  /** Whether it changes the nodes it is given, or what the one node holds. */
  actsOn: ActionInfo["acts_on"]
  fields: FieldSpec[]
}

export function toCommands(actions: ActionInfo[]): ActionCommand[] {
  return actions.map((action) => ({
    name: action.name,
    label: action.title,
    destructive: action.destructive,
    takesFile: action.takes_file,
    previews: action.previews,
    downloads: action.downloads,
    actsOn: action.acts_on,
    fields: schemaToFields(action.params_schema as unknown as JsonSchema),
  }))
}

/** One line of the menu: what it would be done to, and whether it may be. */
export interface MenuCommand extends ActionCommand {
  /** The nodes the filled form is applied to. `[null]` is the root. */
  targets: (string | null)[]
  enabled: boolean
}

/**
 * The menu of what can be done here, in the order the server listed it.
 *
 * Every action the source has is a line, whether or not it applies: a menu
 * that lost its entries as the user walked the catalog would teach nobody what
 * the source can do. What decides each line is the answer of the server —
 * `here` for the places being looked at, `picked` for what is ticked — and
 * which of the two a line reads follows from `acts_on`, never from its name.
 * Ticking nothing therefore leaves everything that changes a node greyed out:
 * standing in a folder is not the same as choosing it.
 *
 * `places` is where something new would be made. A source that offers
 * groupings shows the contents of the ones that are ticked, and those are the
 * places — a table is made in a schema, and a schema is a grouping rather than
 * a folder one walks into. Where there are none, the place is the level
 * itself, which is what a file source has.
 */
export function toMenu(
  here: ActionInfo[],
  picked: ActionInfo[],
  places: (string | null)[],
  checkedIds: string[]
): MenuCommand[] {
  const admitted = new Set(
    picked.filter((action) => action.applicable).map((action) => action.name)
  )
  const applicableHere = new Set(
    here.filter((action) => action.applicable).map((action) => action.name)
  )
  return toCommands(here).map((command) =>
    command.actsOn === "children"
      ? {
          ...command,
          targets: [...places],
          enabled: places.length > 0 && applicableHere.has(command.name),
        }
      : {
          ...command,
          targets: [...checkedIds],
          enabled: checkedIds.length > 0 && admitted.has(command.name),
        }
  )
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

export function replacementsOf(outcome: ActionOutcome) {
  return outcome.done.flatMap((result) =>
    result.replacement === null || result.replacement === undefined
      ? []
      : [result.replacement]
  )
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
