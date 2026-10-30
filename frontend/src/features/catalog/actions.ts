import type { ActionInfo, ActionResult } from "@/client"
import { choicesOf, defaultsOf, schemaToFields } from "@/shared/SchemaForm/jsonSchema"
import type { FieldSpec, JsonSchema, SchemaChoice } from "@/shared/SchemaForm/jsonSchema"
import { t } from "@/shared/i18n"
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
  /** The submenu the source draws it in, or null for a line of the menu itself (D207). */
  menuGroup?: string | null
  /** Whether the source says, for one node, what some of its fields are. */
  offersHints?: boolean
  fields: FieldSpec[]
  /**
   * Values the form opens with that nobody types: what the source made of
   * rows picked in a report (D209).
   */
  preset?: Record<string, unknown>
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
      menuGroup: action.menu_group ?? null,
      offersHints: action.offers_hints === true,
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
  /** What the source calls it, where it calls a schema a database (D229). */
  term?: "database"
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

/**
 * The command as it opens over rows picked in a report (D209).
 *
 * The source said which node the rows belong to, what the form is set to and
 * which fields that stands in for; those fields are left out of the form
 * rather than shown empty, so nothing asks for a window nobody needs.
 */
export function withPickedRows(
  command: ActionCommand,
  target: { params: Record<string, unknown>; replaces?: string[] }
): ActionCommand {
  const replaced = new Set(target.replaces ?? [])
  return {
    ...command,
    fields: command.fields.filter((field) => !replaced.has(field.name)),
    preset: target.params,
  }
}

/** What one node makes of an action's fields, as the source says once the form is open. */
export interface FieldHints {
  choices?: Record<string, SchemaChoice[]>
  /** Fields declared as instants that take a whole number here, with what it is. */
  integers?: Record<string, string>
}

/**
 * The fields as this node has them.
 *
 * A column or an index is the node's, so the schema can only say "a string";
 * the source names them, and a field gets a list instead of a box (D9). A
 * field it left out, or named nothing for, stays typed: an empty list would be
 * a field nobody can fill. A bound is an instant on one hypertable and a value
 * of an integer column on another, so such a field loses its calendar there
 * and says what number it takes.
 */
export function withFieldHints(fields: FieldSpec[], hints: FieldHints | undefined): FieldSpec[] {
  if (hints === undefined) return fields
  const choices = hints.choices ?? {}
  const integers = hints.integers ?? {}
  return fields.map((field) => {
    const offered = choices[field.name]
    if (offered && offered.length > 0 && field.kind === "text") {
      return { ...field, kind: "select", choices: offered }
    }
    const integer = integers[field.name]
    if (integer !== undefined && field.kind === "datetime") {
      return { ...field, kind: "text", description: integer, example: undefined }
    }
    return field
  })
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

/**
 * What the vocabulary says of ticked nodes, by their kinds alone.
 *
 * Not asked of the server per tick: on a distant server that answer took
 * seconds a node, and the run asks again anyway, so a refusal arrives as the
 * run's own answer for the node it was about. The rules are the server's
 * (`action_availability`): every target of a kind the action is for, and one
 * target unless the action takes several.
 */
export function byKind(vocabulary: ActionInfo[], kinds: string[]): ActionInfo[] {
  return vocabulary.map((action) => {
    let reason: string | null = null
    if (kinds.length === 0 || !kinds.every((kind) => (action.applies_to as string[]).includes(kind))) {
      reason = t("catalog.actions.not_for_targets")
    } else if (kinds.length > 1 && action.bulk !== true) {
      reason = t(action.acts_on === "group" ? "catalog.actions.one_grouping" : "catalog.actions.one_target")
    }
    return { ...action, applicable: reason === null, unavailable_reason: reason }
  })
}

/**
 * The kinds a tick box is drawn for: what some command of the catalog's menu
 * acts on. A section of reports and the reports in it are what a connection
 * says about itself, and nothing in the menu is done to them.
 */
export function tickableKinds(vocabulary: ActionInfo[]): Set<string> {
  return new Set(
    vocabulary
      .filter((action) => action.offered_in === "catalog" && (action.acts_on === "node" || action.acts_on === "group"))
      .flatMap((action) => action.applies_to as string[])
  )
}

/** Why a line is off when its subject is empty, keyed by what it acts on. */
function noTarget(actsOn: ActionInfo["acts_on"]): string {
  return t(`catalog.actions.no_target.${actsOn}`)
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
        ? noTarget(command.actsOn)
        : answer?.unavailable_reason ?? t("catalog.actions.not_for_targets")
    return { ...command, targets, enabled, reason }
  })
}

/**
 * Lines of one family folded into a submenu where the first of them stood.
 *
 * The family is the source's word (D207): a client deciding which commands
 * belong together would be a table of action names on this side. The submenu
 * is usable while any line in it is, and never hides a disabled line.
 */
export function withSubmenus(lines: (MenuItem & { group?: string | null })[]): MenuItem[] {
  const menu: MenuItem[] = []
  const submenus = new Map<string, MenuItem & { children: MenuItem[] }>()
  for (const { group, ...line } of lines) {
    if (group === null || group === undefined) {
      menu.push(line)
      continue
    }
    let submenu = submenus.get(group)
    if (submenu === undefined) {
      submenu = { name: `group:${group}`, label: group, children: [] }
      submenus.set(group, submenu)
      menu.push(submenu)
    }
    submenu.children.push(line)
  }
  for (const submenu of submenus.values()) {
    submenu.disable = submenu.children.every((child) => child.disable === true)
  }
  return menu
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
  "details", "relationships", "copy", "cut", "backups", "searchIndex",
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
  /**
   * Whether this connection could keep a list of its names for search, and
   * why not (D212). Offered on every connection, so the line is found where
   * a person looks for what can be done to one; disabled with the reason on
   * a type that cannot say its names.
   */
  searchIndex?: { enabled: boolean; reason?: string }
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
      label: t("catalog.actions.details"),
      disable: !state.describable,
      hint: state.describable ? undefined : t("catalog.actions.details_hint"),
    })
  }
  if (state.diagrams) {
    items.push({
      name: clientCommandName("relationships"),
      label: t("catalog.actions.relationships"),
      disable: !state.diagrammable,
      hint: state.diagrammable ? undefined : t("catalog.actions.relationships_hint"),
    })
  }
  if (state.copy) {
    items.push({
      name: clientCommandName("copy"),
      label: t("catalog.actions.copy"),
      disable: !state.copy.enabled,
      hint: state.copy.reason,
    })
  }
  if (state.cut) {
    items.push({
      name: clientCommandName("cut"),
      label: t("catalog.actions.cut"),
      disable: !state.cut.enabled,
      hint: state.cut.reason,
    })
  }
  // Last of the client's, because it is the one line about the connection
  // rather than about anything picked out inside it.
  if (state.backups) {
    items.push({
      name: clientCommandName("backups"),
      label: t("catalog.actions.backups"),
      disable: !state.backups.enabled,
      hint: state.backups.reason,
    })
  }
  if (state.searchIndex) {
    items.push({
      name: clientCommandName("searchIndex"),
      label: t("catalog.actions.search_index"),
      disable: !state.searchIndex.enabled,
      hint: state.searchIndex.reason,
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
  /** How many targets were done, where one result stands for several: a set. */
  doneCount?: number
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
    return first?.message ?? t("catalog.actions.done", { label })
  }
  const stopped = outcome.skipped?.length ?? 0
  const head = t("catalog.actions.done_of", { label, done: outcome.doneCount ?? outcome.done.length, total: outcome.total }) +
    (stopped > 0 ? `. ${t("catalog.actions.stopped", { n: stopped }, stopped)}` : "")
  if (outcome.failures.length === 0) return head
  const said = outcome.failures
    .map((failure) => `${subjectOf(failure)} — ${failure.message}`)
    .join("; ")
  return `${head}. ${said}`
}
