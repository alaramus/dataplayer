import type { ActionInfo, ActionResult } from "@/client"
import { choicesOf, defaultsOf, schemaToFields } from "@/shared/SchemaForm/jsonSchema"
import type { FieldSpec, JsonSchema, SchemaChoice } from "@/shared/SchemaForm/jsonSchema"
import type { MenuItem } from "@/shared/ui"

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
  /**
   * What the confirmation asks, when the action has words of its own.
   *
   * Null for everything that removes what it names: the client's own sentence
   * names the node, which is better. An action that is destructive without
   * being a deletion says so itself, because only it knows the difference.
   */
  question: string | null
  takesFile: boolean
  /** Whether one filled form may carry several files, a request each. */
  takesManyFiles: boolean
  /** Whether the source can say what this would do before it is done. */
  previews: boolean
  /**
   * Whether a selection is done in one request rather than one per node.
   *
   * The difference is visible: repeated requests report a refusal per node and
   * leave what did land landed, while one request either happens or does not.
   * Which of the two an action is belongs to the action, so it is read off the
   * answer rather than decided here.
   */
  takesSet: boolean
  /** Whether that one request can be asked what it would do. */
  previewsSet: boolean
  /** Whether the action returns one native browser download for all targets. */
  downloads: boolean
  /** Opens the ordinary connector form with values prepared by the source. */
  preparesConnector?: boolean
  requiresPlanReview?: boolean
  /**
   * Whether the server carries it out as an owned job: the request is
   * accepted and the work is followed in Activity, never awaited here (D123).
   */
  producesJob?: boolean
  /** Which selection subject or destination candidates the action receives. */
  actsOn: ActionInfo["acts_on"]
  /**
   * Where the source wants it offered: this menu, or the row of commands above
   * the rows of the node it acts on. Making a database user belongs over the
   * list of users, not behind a tick in the catalog (D79).
   */
  offeredIn: ActionInfo["offered_in"]
  /**
   * What to draw for it where it is a picture rather than a line of a menu.
   * Null everywhere the title is what is read; the source names it, because a
   * client choosing one would be a table of action names on this side.
   */
  icon: string | null
  fields: FieldSpec[]
  /** What each field with a published set of values offers, by field name. */
  choices: Record<string, SchemaChoice[]>
  /** What each field starts as, by field name. */
  defaults: Record<string, unknown>
  workflow?: JsonSchema["x-ui-workflow"]
}

export function toCommands(actions: ActionInfo[]): ActionCommand[] {
  return actions.map((action) => {
    const schema = action.params_schema as unknown as JsonSchema
    return {
      name: action.name,
      label: action.title,
      destructive: action.destructive,
      question: action.question ?? null,
      takesFile: action.takes_file,
      takesManyFiles: action.takes_many_files,
      previews: action.previews,
      takesSet: action.takes_set,
      previewsSet: action.previews_set,
      downloads: action.downloads,
      preparesConnector: action.prepares_connector === true,
      requiresPlanReview: action.requires_plan_review === true,
      producesJob: action.produces_job === true,
      actsOn: action.acts_on,
      offeredIn: action.offered_in,
      icon: action.icon ?? null,
      fields: schema["x-ui-workflow"] === undefined ? schemaToFields(schema) : [],
      // Read whether or not a form is built: a workflow screen still asks the
      // schema what the source offers, in the source's own words.
      choices: choicesOf(schema),
      defaults: defaultsOf(schema),
      workflow: schema["x-ui-workflow"],
    }
  })
}

/** One grouping a level offers, as much of it as a form needs. */
export interface Grouping {
  id: string
  label: string
  /** Whether the source considers it part of its own machinery. */
  system: boolean
}

/**
 * The groupings a form may send, in the order the level lists them.
 *
 * A source's own machinery is left out: `pg_catalog` is a real schema and is
 * shown in the catalog for that reason, but offering it as a place to move a
 * table into is offering something every source refuses. Ids and not names —
 * the value travels back to the source that issued it, and nothing here reads
 * what one is made of (D21).
 */
export function groupingChoices(groupings: Grouping[]): SchemaChoice[] {
  return groupings
    .filter((grouping) => !grouping.system)
    .map((grouping) => ({ value: grouping.id, label: grouping.label }))
}

/**
 * The fields of a form, with a field that names a grouping made a choice.
 *
 * The schema cannot carry the list: groupings belong to one connection and the
 * schema is declared by the adapter class, so the server says what the field
 * means and the client fills in what this connection has. Nothing is changed
 * where there is nothing to choose from — a select with no options is a dead
 * end, and the name can still be typed.
 */
export function withGroupingChoices(
  fields: FieldSpec[],
  choices: SchemaChoice[]
): FieldSpec[] {
  if (choices.length === 0) return fields
  return fields.map((field) =>
    field.purpose === "grouping" ? { ...field, kind: "select", choices } : field
  )
}

/** One line of the stable menu and what it will be done to. */
export interface MenuCommand extends ActionCommand {
  /** The nodes the filled form is applied to. `[null]` is the root. */
  targets: (string | null)[]
  enabled: boolean
  /** Missing UI selection or the source's reason for refusing these targets. */
  reason: string | null
}

export interface ActionSubject {
  actions: ActionInfo[]
  targets: (string | null)[]
}

export type ActionSubjects = Record<ActionInfo["acts_on"], ActionSubject>

const NO_TARGET: Record<ActionInfo["acts_on"], string> = {
  level: "This source does not offer it at this level",
  children: "There is nowhere here to put it",
  node: "Tick a row to use this",
  group: "Select a grouping to use this",
  destination: "No available destination here",
}

/** Resolve each action against its own subject, including its form target (D118). */
export function toMenu(subjects: ActionSubjects): MenuCommand[] {
  const offered = subjects.level.actions.filter((action) => action.offered_in === "catalog")
  return toCommands(offered).map((command) => {
    const subject = subjects[command.actsOn]
    const answer = subject.actions.find((action) => action.name === command.name)
    // A destination workflow chooses one place; candidates must never become a batch.
    const targets = command.actsOn === "destination"
      ? (answer?.available_node_ids ?? []).slice(0, 1)
      : [...subject.targets]
    const enabled = targets.length > 0 && answer?.applicable === true
    const reason = enabled
      ? null
      : targets.length === 0
        ? NO_TARGET[command.actsOn]
        : answer?.unavailable_reason ?? "This source does not offer it for these targets"
    return { ...command, targets, enabled, reason }
  })
}

/**
 * Whether this command is one the catalog's clipboard fills.
 *
 * Asked of the fields rather than of the name: the source says a field is for
 * what was copied, and the client fills it. A command like this is offered
 * only while something is held, because an empty one is a form nobody can
 * complete (D74).
 */
export function needsClipboard(command: ActionCommand): boolean {
  return command.fields.some((field) => field.purpose === "clipboard-nodes")
}

/**
 * The selection as a set, or nothing when it is not one.
 *
 * The root of a connector travels as null and has no id to put in a list, so
 * a selection holding one is not a set. One function because two callers must
 * agree: what is previewed as a set and what is sent as a set are the same
 * selection, and a disagreement would show a person the consequences of a
 * request that is never made.
 */
export function nodeSetOf(nodeIds: (string | null)[]): string[] | null {
  const named = nodeIds.filter((id): id is string => id !== null)
  return named.length === nodeIds.length && named.length > 0 ? named : null
}

/**
 * The verbs the client owns, in the same menu as the source's own; none of
 * them reaches the server as a command (D74, D75, D97). One menu rather than a
 * row of icons that grows with every client verb.
 *
 * The names are prefixed because one menu carries two vocabularies: a source
 * names its actions with identifiers, so a colon cannot collide.
 */
export const CLIENT_COMMANDS = [
  "details", "relationships", "copy", "cut", "describe-table", "backups",
] as const
export type ClientCommand = (typeof CLIENT_COMMANDS)[number]

export function clientCommandName(command: ClientCommand): string {
  return `client:${command}`
}

export function clientCommandOf(name: string): ClientCommand | null {
  return CLIENT_COMMANDS.find((command) => clientCommandName(command) === name) ?? null
}

export interface ClientMenuState {
  /** Whether the source describes the nodes of this level at all (D75). */
  describes: boolean
  /** Whether exactly one ticked node is one it describes. */
  describable: boolean
  /** Whether this source draws the structure of what it holds at all (D97). */
  diagrams: boolean
  /** Whether the set that would be drawn is one a diagram can hold. */
  diagrammable: boolean
  /**
   * Whether the ticked nodes can be put on the clipboard, and why not.
   *
   * Absent when nothing takes this source's nodes that way — neither its own
   * Paste (D74) nor one in another connection (D164) — so the line would be
   * a promise nothing keeps.
   */
  copy?: { enabled: boolean; reason?: string }
  cut?: { enabled: boolean; reason?: string }
  /**
   * Whether the selection can be described as a table, and why not (D170).
   *
   * Absent for a source over which nothing can be declared: only a type that
   * says `declared_tables` shows the line.
   */
  table?: { enabled: boolean; reason?: string }
  /**
   * Whether this connection could be copied out, and why not when it cannot.
   *
   * Absent when this kind of source cannot be copied out at all: only a type
   * whose driver can name a program that dumps it declares the `backup`
   * capability, and neither a file source nor a Redis server does. The other
   * half of the question is about the machine — a container runtime to run the
   * dump in and somewhere to write what it produces (D87) — and that is the
   * refusal carried here.
   */
  backups?: { enabled: boolean; reason?: string }
}

/**
 * The client's lines of the menu, before the source's.
 *
 * Each is drawn only where it means anything — a key store has nothing to
 * copy anywhere — and disabled rather than hidden while the
 * selection is not the one it needs, so the menu keeps the stable shape the
 * source's own lines have.
 */
export function clientMenu(state: ClientMenuState): MenuItem[] {
  const items: MenuItem[] = []
  if (state.describes) {
    items.push({
      name: clientCommandName("details"),
      label: "Details",
      disable: !state.describable,
      hint: state.describable ? undefined : "Tick one row to describe",
    })
  }
  if (state.diagrams) {
    items.push({
      name: clientCommandName("relationships"),
      label: "Relationships",
      disable: !state.diagrammable,
      hint: state.diagrammable ? undefined : "Nothing here has a structure to draw",
    })
  }
  if (state.copy) {
    items.push({
      name: clientCommandName("copy"),
      label: "Copy",
      disable: !state.copy.enabled,
      hint: state.copy.reason,
    })
  }
  if (state.cut) {
    items.push({
      name: clientCommandName("cut"),
      label: "Cut",
      disable: !state.cut.enabled,
      hint: state.cut.reason,
    })
  }
  if (state.table) {
    items.push({
      name: clientCommandName("describe-table"),
      label: "Describe as table",
      disable: !state.table.enabled,
      hint: state.table.reason,
    })
  }
  // Last of the client's, because it is the one line about the connection
  // rather than about anything picked out inside it.
  if (state.backups) {
    items.push({
      name: clientCommandName("backups"),
      label: "Backups",
      disable: !state.backups.enabled,
      hint: state.backups.reason,
    })
  }
  return items
}

/** One request the action could not be done by, and what the server said. */
export interface ActionFailure {
  nodeId: string | null
  message: string
  /** The file that request was carrying, when it was carrying one. */
  file?: File
  /** Whether the source refused because the name is already taken. */
  conflict?: boolean
}

/** What became of one filled form applied to a set of nodes. */
export interface ActionOutcome {
  done: ActionResult[]
  failures: ActionFailure[]
  total: number
  /** Unsent requests after Stop. Completed effects have not been undone. */
  skipped?: ActionFailure[]
}

/**
 * What stays ticked once an action has been carried out.
 *
 * Only what it could not be carried out on: a tick left on what was done
 * offers it for the same action again, and one left on a copied file made the
 * next Paste aim at that file rather than at the folder. What failed stays
 * ticked so a retry is one click, and an action that did nothing at all
 * leaves the ticks as they were.
 */
export function ticksAfter(ticked: string[], outcome: ActionOutcome): string[] {
  if (outcome.done.length === 0) return ticked
  const unfinished = new Set(
    [...outcome.failures, ...(outcome.skipped ?? [])].map((failure) => failure.nodeId)
  )
  return ticked.filter((id) => unfinished.has(id))
}

/**
 * The branches to re-read, each named once.
 *
 * Deleting five files out of one folder names that folder five times; reading
 * it five times would only produce the same answer four times over.
 */
export function reloadedBy(outcome: ActionOutcome): (string | null)[] {
  const seen = new Set<string | null>()
  for (const result of outcome.done) {
    for (const nodeId of result.reload_node_ids) seen.add(nodeId)
  }
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
 * What one refusal was about.
 *
 * The file when the request carried one: three files going into the same
 * folder are three requests about the same node, and naming that node three
 * times would say nothing about which of them was refused.
 */
function subjectOf(failure: ActionFailure): string {
  return failure.file?.name ?? failure.nodeId ?? "?"
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
  const stopped = outcome.skipped?.length ?? 0
  const head = `${label}: ${String(outcome.done.length)} of ${String(outcome.total)}` +
    (stopped > 0 ? `. Stopped; ${stopped} not started` : "")
  if (outcome.failures.length === 0) return head
  const said = outcome.failures
    .map((failure) => `${subjectOf(failure)} — ${failure.message}`)
    .join("; ")
  return `${head}. ${said}`
}
