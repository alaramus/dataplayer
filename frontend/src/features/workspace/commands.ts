/**
 * The commands that belong to a connection rather than to anything on screen.
 *
 * A console is written against a connection and belongs to a person, so there
 * is no node whose toolbar it could live in; it used to be squeezed in beside
 * the plus in the connections column. The bar at the foot of the screen is
 * where those go, under one rule: offered while a connection is being read and
 * that connection can do the thing. Plain functions, so the rule is tested in
 * one place rather than inferred from a row of `v-if`s.
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

/**
 * The library of queries, which is a person's rather than a connection's.
 *
 * In the bar with the connection's own commands because that is where a
 * person looks for it, but never disabled with them: a query outlives the
 * connection it was written against (D63), and the library has a filter of
 * its own for choosing which connection to look at. It used to be greyed out
 * until a catalog was open, which made the one place your own work lives
 * reachable only through somebody else's database.
 */
export function queriesCommand(state: ConnectionState): ConnectionCommand {
  const about =
    state.name !== null && state.supportsQueries === "yes"
      ? `Queries written against ${state.name}`
      : "Every query you have written"
  return {
    name: "queries",
    label: "Queries",
    icon: "manage_search",
    enabled: true,
    tooltip: about,
  }
}

export function connectionCommands(state: ConnectionState): ConnectionCommand[] {
  return [
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
