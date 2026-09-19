import type { AdapterTypeInfo, ConnectorPublic } from "@/client"

import type { LinkState } from "./terminalLink"

/**
 * What decides where a terminal opens and what it is called, as plain
 * functions: the rail button and the panel both ask, and a test asks without
 * either (D149).
 */

/** An open terminal as these questions see it. */
export interface OpenTerminal {
  id: string
  connectorId: string
  /** Its number among the terminals of one connection, kept while it is open. */
  ordinal: number
}

/**
 * The connections a terminal can be opened on: one's own, switched on, of a
 * type whose driver has a shell. A grant never includes one, so a shared
 * connection is not offered only to be refused.
 */
export function terminalCandidates(
  connectors: readonly ConnectorPublic[],
  types: readonly AdapterTypeInfo[]
): ConnectorPublic[] {
  const withShell = new Set(
    types
      .filter((type) => type.capabilities.some((capability) => capability.code === "terminal"))
      .map((type) => type.name)
  )
  return connectors.filter(
    (connector) =>
      connector.access === "own" && connector.enabled && withShell.has(connector.adapter_type)
  )
}

export type TerminalPress =
  | { kind: "hide" }
  /** Show the panel as it is: nothing open says what can be. */
  | { kind: "show" }
  /** The connection being worked in has a terminal already: bring it forward. */
  | { kind: "select"; terminalId: string }
  /** The connection being worked in has none yet: open one on it. */
  | { kind: "open"; connectorId: string }

/**
 * What pressing the Terminals button on the rail does.
 *
 * The button is the tool's switch, as every button of the panel is (D143),
 * so pressing it while the tool is shown hides it. Otherwise it goes to the
 * connection being worked in when a terminal can be opened there, and to the
 * panel's own choice when not.
 */
export function terminalPress(state: {
  shown: boolean
  activeConnectorId: string | null
  candidateIds: readonly string[]
  open: readonly OpenTerminal[]
}): TerminalPress {
  if (state.shown) return { kind: "hide" }
  const here = state.activeConnectorId
  if (here === null || !state.candidateIds.includes(here)) return { kind: "show" }
  const existing = state.open.filter((terminal) => terminal.connectorId === here)
  const latest = existing.at(-1)
  return latest === undefined
    ? { kind: "open", connectorId: here }
    : { kind: "select", terminalId: latest.id }
}

/** What the button says it will do, for its tooltip. */
export function terminalPressTooltip(press: TerminalPress, connectorName: string | null): string {
  switch (press.kind) {
    case "hide":
      return "Hide the terminals"
    case "open":
      return connectorName === null ? "Open a terminal" : `Open a terminal on ${connectorName}`
    case "select":
      return connectorName === null ? "Terminals" : `Terminal on ${connectorName}`
    case "show":
      return "Terminals"
  }
}

/**
 * The number a new terminal of a connection takes: one past the highest open.
 *
 * Not a count, so closing the second of three leaves the third called 3
 * rather than renaming it under the person's eyes.
 */
export function nextOrdinal(open: readonly OpenTerminal[], connectorId: string): number {
  const taken = open
    .filter((terminal) => terminal.connectorId === connectorId)
    .map((terminal) => terminal.ordinal)
  return taken.length === 0 ? 1 : Math.max(...taken) + 1
}

/** A terminal's tab: the connection's name now, and its number past the first. */
export function terminalTitle(terminal: OpenTerminal, connectorName: string | null): string {
  const name = connectorName ?? "Connection"
  return terminal.ordinal === 1 ? name : `${name} (${String(terminal.ordinal)})`
}

/** Which terminal comes forward when one is closed: its neighbour, if any. */
export function afterClosing(
  open: readonly OpenTerminal[],
  closing: string,
  active: string | null
): string | null {
  if (active !== closing) return active
  const index = open.findIndex((terminal) => terminal.id === closing)
  const rest = open.filter((terminal) => terminal.id !== closing)
  if (rest.length === 0) return null
  return rest[Math.min(index, rest.length - 1)].id
}

export interface TerminalNotice {
  tone: "info" | "warning" | "error"
  text: string
  /** What the one button beside it does. */
  action: "unlock" | "again" | null
}

/**
 * What is said above a terminal that is not simply running.
 *
 * A locked key is the one refusal with a way on that is not trying again as
 * it was (D147); everything else that stopped offers exactly that.
 */
export function terminalNotice(state: LinkState): TerminalNotice | null {
  switch (state.kind) {
    case "open":
      return null
    case "connecting":
      return { tone: "info", text: "Connecting…", action: null }
    case "refused":
      return {
        tone: "error",
        text: state.message,
        action: state.errorKind === "locked" ? "unlock" : "again",
      }
    case "ended":
      return {
        tone: "info",
        text:
          state.exitStatus === null || state.exitStatus === 0
            ? "The shell has ended"
            : `The shell has ended with status ${String(state.exitStatus)}`,
        action: "again",
      }
    case "lost":
      return { tone: "warning", text: "The connection to the server was lost", action: "again" }
  }
}
