import type { PreparedScript, PreparedStatement, RunParameter } from "@/client"
import { t } from "@/shared/i18n"
import { formatFixed } from "@/shared/i18n/format"

/**
 * What Run means, worked out from what the source said and where the caret is.
 *
 * Plain functions, so the rules can be tested without an editor: which
 * statement a caret is in, what a selection means, and what a parameter form
 * has to ask for. The ranges come from the source's own parser — the browser
 * never decides where a statement ends (D62).
 */

/** One press of Run: the text to send, and where it came from. */
export interface RunTarget {
  text: string
  start: number
  end: number
  scope: "statement" | "script"
  /**
   * For a fragment selected inside one statement, that statement: run instead
   * when the source does not read the fragment as a statement of its own (D65).
   */
  enclosing?: RunTarget
}

/**
 * The statement the caret is in.
 *
 * A caret sitting between two statements belongs to the one before it: that is
 * where somebody who has just finished typing has left it.
 */
export function statementAt(
  script: PreparedScript,
  caret: number
): PreparedStatement | null {
  let candidate: PreparedStatement | null = null
  for (const statement of script.statements) {
    if (statement.start > caret) break
    candidate = statement
  }
  if (candidate === null) {
    return script.statements[0] ?? null
  }
  return candidate
}

/**
 * What Ctrl+Enter runs: the selection, or the statement under the caret.
 *
 * Never the whole document. A selection is taken as it is — with several
 * statements in it, it is a script and the caller says so — and running the
 * document is the other command (D65). A fragment of one statement carries
 * that statement along, for when the fragment is not one by itself: undo
 * leaves restored text selected, and that text is rarely a statement.
 */
export function targetFor(
  script: PreparedScript,
  text: string,
  selection: { from: number; to: number }
): RunTarget | null {
  if (selection.to > selection.from) {
    const selected = text.slice(selection.from, selection.to)
    if (selected.trim() === "") return null
    const inside = script.statements.filter(
      (statement) => statement.start < selection.to && statement.end > selection.from
    )
    // A selection holding no statement at all — a semicolon, a blank line, a
    // comment — is nothing to run, and saying so here saves a refusal.
    if (inside.length === 0) return null
    if (inside.length === 1) {
      const only = inside[0]!
      const statement: RunTarget = { text: only.text, start: only.start, end: only.end, scope: "statement" }
      if (selection.from <= only.start && selection.to >= only.end) return statement
      return {
        text: selected,
        start: selection.from,
        end: selection.to,
        scope: "statement",
        enclosing: statement,
      }
    }
    return {
      text: selected,
      start: selection.from,
      end: selection.to,
      scope: "script",
    }
  }
  const statement = statementAt(script, selection.from)
  if (statement === null) return null
  return {
    text: statement.text,
    start: statement.start,
    end: statement.end,
    scope: "statement",
  }
}

/** Whether the source read a fragment as something other than statements. */
export function unreadable(script: PreparedScript): boolean {
  return script.statements.length === 0 || script.statements.some((one) => one.kind === "unknown")
}

/** What Ctrl+Shift+Enter runs: everything, said explicitly. */
export function wholeDocument(script: PreparedScript, text: string): RunTarget | null {
  if (script.statements.length === 0) return null
  return {
    text,
    start: 0,
    end: text.length,
    scope: script.statements.length > 1 ? "script" : "statement",
  }
}

/** One row of the form a run with parameters asks for first. */
export interface ParameterEntry {
  name: string
  value: string
  isNull: boolean
  secret: boolean
  remember: boolean
}

/**
 * The form for this script, keeping what the person already filled in.
 *
 * A value the document remembers fills its row; a secret one never does, which
 * is what "a secret value is never retained" looks like from here (D63).
 */
export function parameterForm(
  names: string[],
  remembered: Record<string, string | null>,
  current: ParameterEntry[] = []
): ParameterEntry[] {
  const held = new Map(current.map((entry) => [entry.name, entry]))
  return names.map((name) => {
    const kept = held.get(name)
    if (kept !== undefined) return kept
    const value = remembered[name]
    return {
      name,
      value: value ?? "",
      isNull: value === null && name in remembered,
      secret: false,
      remember: name in remembered,
    }
  })
}

export function bindingsOf(entries: ParameterEntry[]): RunParameter[] {
  return entries.map((entry) => ({
    name: entry.name,
    value: entry.isNull ? null : entry.value,
    secret: entry.secret,
  }))
}

/**
 * What the document should remember after a run.
 *
 * Only what was marked to remember, and never a secret: a value marked secret
 * is used and forgotten.
 */
export function toRemember(entries: ParameterEntry[]): Record<string, string | null> {
  const kept: Record<string, string | null> = {}
  for (const entry of entries) {
    if (!entry.remember || entry.secret) continue
    kept[entry.name] = entry.isNull ? null : entry.value
  }
  return kept
}

/** Whether every parameter has an answer, so Run may be offered at all. */
export function ready(entries: ParameterEntry[]): boolean {
  return entries.every((entry) => entry.isNull || entry.value !== "")
}

const STATUSES = [
  "pending",
  "accepted",
  "running",
  "cancelling",
  "cancelled",
  "succeeded",
  "failed",
  "timed_out",
  "interrupted",
  "not_run",
] as const

/** A run's or a statement's status as a word; one this build does not know stays as sent. */
export function statusWord(status: string): string {
  const known = STATUSES.find((one) => one === status)
  return known === undefined ? status : t(`queries.status.${known}`)
}

/** How long a run has been going, as a person reads it. */
export function elapsed(milliseconds: number): string {
  if (milliseconds < 1000) return t("queries.duration.ms", { n: milliseconds })
  const seconds = milliseconds / 1000
  if (seconds < 60) return t("queries.duration.seconds_fraction", { n: formatFixed(seconds, 1) })
  const minutes = Math.floor(seconds / 60)
  return t("queries.duration.minutes_seconds", { m: minutes, s: Math.floor(seconds % 60) })
}
