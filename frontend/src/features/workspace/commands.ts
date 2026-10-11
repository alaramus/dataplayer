import { appIcons } from "@/shared/ui/icons"

/**
 * The commands in the bar at the foot of the screen.
 *
 * A console is written against a connection and belongs to a person, so there
 * is no node whose toolbar it could live in; it used to be squeezed in beside
 * the plus in the connections column. What acts on the open connection lives
 * in the connection's own menu instead — copying a database out went there —
 * and what is left here belongs to the person or to the server. Plain
 * functions, so the rule is tested in one place rather than inferred from a
 * row of `v-if`s.
 */

/** What a connection has answered about one capability, including "not yet". */
export type Support = "yes" | "no" | "asking"

export interface ConnectionState {
  /** The connection being read, or null when none is. */
  name: string | null
  supportsQueries: Support
}

export interface ConnectionCommand {
  name: string
  label: string
  icon: string
  enabled: boolean
  /** What pressing it would do, or why it cannot be pressed. */
  tooltip: string
}

/**
 * The library of queries, which is a person's rather than a connection's.
 *
 * Never disabled: a query outlives the connection it was written against
 * (D63), and the library has a filter of its own for choosing which
 * connection to look at. It used to be greyed out until a catalog was open,
 * which made the one place your own work lives reachable only through
 * somebody else's database.
 */
export function queriesCommand(state: ConnectionState): ConnectionCommand {
  const about =
    state.name !== null && state.supportsQueries === "yes"
      ? `Queries written against ${state.name}`
      : "Every query you have written"
  return {
    name: "queries",
    label: "Queries",
    icon: appIcons.code,
    enabled: true,
    tooltip: about,
  }
}

/**
 * The one command in the bar that is not about a connection: what this server
 * is running belongs to the person rather than to whatever is open.
 *
 * The button stays in place whether or not there is anything to open, for the
 * reason the rest of the bar does — a bar that changes shape as the user walks
 * about is a bar they have to read every time.
 */
export interface ServicesState {
  /** How many services this person has here. */
  count: number
  /** How many of them are running now. */
  running: number
  /** What is happening to one of them, if anything is, in the server's words. */
  working: string | null
}

/** Of the services here, how many run: all of them is the common case. */
function runningTooltip(running: number, count: number): string {
  if (running === count) {
    return count === 1 ? "One service is running here" : `${String(count)} services are running here`
  }
  if (running === 0) {
    return count === 1
      ? "Your one service here is stopped"
      : `None of your ${String(count)} services here is running`
  }
  return `${String(running)} of ${String(count)} services are running here`
}

export function servicesCommand(state: ServicesState): ConnectionCommand {
  if (state.working !== null) {
    return {
      name: "services",
      label: "Services",
      icon: appIcons.dns,
      enabled: true,
      // While something is happening, the button is where it is said: this is
      // the only place a start is visible once the dialog that asked for it
      // has closed.
      tooltip: state.working,
    }
  }
  if (state.count === 0) {
    // Pressable all the same: the panel it opens says there is nothing, and
    // that is an answer as well (D143).
    return {
      name: "services",
      label: "Services",
      icon: appIcons.dns,
      enabled: true,
      tooltip: "This server is not running anything for you",
    }
  }
  return {
    name: "services",
    label: "Services",
    icon: appIcons.dns,
    enabled: true,
    tooltip: runningTooltip(state.running, state.count),
  }
}
