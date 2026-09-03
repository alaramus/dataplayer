/**
 * The commands that belong to a connection rather than to anything on screen.
 *
 * Most buttons in this application hang off the thing they act on: a table's
 * commands are in its grid, a node's are in the catalog's menu. A few have no
 * such thing. Queries are the first of them — a console is written against a
 * connection and belongs to a person, so there is no node whose toolbar it
 * could live in, and it ended up beside the plus in the connections column
 * where nothing else of its kind would fit.
 *
 * The bar at the foot of the screen is where those go. Its rule is one
 * sentence: a command is offered while a connection is being read and that
 * connection can do the thing. Everything here is a plain function, so the
 * rule can be read and tested in one place rather than inferred from a row of
 * `v-if`s.
 */

/** What a connection has answered about one capability, including "not yet". */
export type Support = "yes" | "no" | "asking"

export interface ConnectionState {
  /** The connection being read, or null when none is. */
  name: string | null
  supportsQueries: Support
  /**
   * Whether this connection could be copied out, which is two questions.
   *
   * One is about the machine — a container runtime to run `pg_dump` in and
   * somewhere to write what it produces (D87) — and the server answers it for
   * the installation. The other is about the source: only a type whose driver
   * can name a program that dumps it declares the `backup` capability, and
   * neither a file source nor a Redis server does. Both must say yes, and the
   * refusal is whichever one said no.
   */
  supportsBackups: Support
  backupsRefusal?: string
}

export interface ConnectionCommand {
  name: string
  label: string
  icon: string
  enabled: boolean
  /** What pressing it would do, or why it cannot be pressed. */
  tooltip: string
}

const NOTHING_OPEN = "Open a connection to use this"
const STILL_ASKING = "Asking this connection what it can do"

export function connectionCommands(state: ConnectionState): ConnectionCommand[] {
  return [
    {
      name: "queries",
      label: "Queries",
      icon: "manage_search",
      ...offered(
        state,
        state.supportsQueries,
        "This source does not run queries",
        (name) => `Queries written against ${name}`
      ),
    },
    {
      name: "backups",
      label: "Backups",
      icon: "inventory_2",
      ...offered(
        state,
        state.supportsBackups,
        state.backupsRefusal ?? "This server cannot copy a database out",
        (name) => `Copy ${name} out, or put a backup back`
      ),
    },
  ]
}

/**
 * Whether one command is offered, and what it says either way.
 *
 * Three answers rather than two, because "we have not asked yet" is not "no".
 * Telling somebody their PostgreSQL connection does not run queries for the
 * half second before the answer arrives is a worse lie than saying nothing.
 */
function offered(
  state: ConnectionState,
  support: Support,
  refusal: string,
  wording: (name: string) => string
): { enabled: boolean; tooltip: string } {
  if (state.name === null) return { enabled: false, tooltip: NOTHING_OPEN }
  if (support === "asking") return { enabled: false, tooltip: STILL_ASKING }
  if (support === "no") return { enabled: false, tooltip: refusal }
  return { enabled: true, tooltip: wording(state.name) }
}

/**
 * The one command in the bar that is not about a connection.
 *
 * What this server is running belongs to the person rather than to whatever
 * is open, so it sits apart from the others. It used to be a list above the
 * connections, in a column a fifth of the screen wide that is also where a
 * hundred and fifty connections go; a service is looked at when something is
 * being done to it and not otherwise, so it is a window now.
 *
 * The button stays in place whether or not there is anything to open, for the
 * reason the rest of the bar does: a bar that changes shape as the user walks
 * about is a bar they have to read every time.
 */
export interface ServicesState {
  /** How many services this person has here. */
  count: number
  /** What is happening to one of them, if anything is, in the server's words. */
  working: string | null
}

export function servicesCommand(state: ServicesState): ConnectionCommand {
  if (state.working !== null) {
    return {
      name: "services",
      label: "Services",
      icon: "dns",
      enabled: true,
      // While something is happening, the button is where it is said: this is
      // the only place a start is visible once the dialog that asked for it
      // has closed.
      tooltip: state.working,
    }
  }
  if (state.count === 0) {
    return {
      name: "services",
      label: "Services",
      icon: "dns",
      enabled: false,
      tooltip: "This server is not running anything for you",
    }
  }
  return {
    name: "services",
    label: "Services",
    icon: "dns",
    enabled: true,
    tooltip:
      state.count === 1
        ? "One service is running here"
        : `${state.count} services are running here`,
  }
}
