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
   * Whether this server could copy a database out at all.
   *
   * Not about the source: about the machine — a container runtime to run
   * `pg_dump` in and somewhere to write what it produces (D87). The server
   * answers it, and the reason it gives is what the button says.
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
