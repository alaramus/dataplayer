import type { PreparedScript, QueryRehearsal, SchemaEffect } from "@/client"

/**
 * Structure changes in the console: what to rehearse, what to say, what to
 * re-read afterwards (D66).
 *
 * Plain functions rather than component code, so each of the three can be
 * tested without a database behind it or a panel around it. None of them
 * decides whether a change may be made — that is the server's answer, four
 * times over — and none of them builds a node id.
 */

/** Whether these statements have to be tried out before they are run. */
export function needsRehearsal(script: PreparedScript | null): boolean {
  return (script?.statements ?? []).some((statement) => statement.destructive === true)
}

/**
 * What the rehearsal found, as the sentence shown before the question.
 *
 * The source's own words, in the source's own order. Nothing is summarised
 * into a count: "drop cascades to view sales_by_month" is the thing worth
 * reading, and "3 objects affected" is not.
 */
export function rehearsalReport(rehearsal: QueryRehearsal): string {
  const lines: string[] = []
  for (const statement of rehearsal.statements ?? []) {
    const place = `Statement ${statement.ordinal + 1}`
    if (statement.outcome === "blocked") {
      lines.push(`${place}: could not be tried — something else is holding it open.`)
      continue
    }
    if (statement.outcome === "failed") {
      lines.push(
        `${place}: the source refused it — ${
          statement.diagnostic?.message ?? "it could not be carried out"
        }.`
      )
      continue
    }
    if (statement.outcome === "not_run") continue
    const tag = statement.command_tag ?? "it would be carried out"
    lines.push(`${place}: ${tag}.`)
    for (const notice of statement.notices ?? []) lines.push(`  ${notice.message}`)
  }
  return lines.join("\n")
}

/**
 * Why the change cannot be run now, when it cannot.
 *
 * A blocked rehearsal is the one answer that disables execution: nothing was
 * learnt, and the real run would wait exactly where this gave up (D66).
 */
export function blockedReason(rehearsal: QueryRehearsal): string | null {
  if (rehearsal.blocked === true) {
    return (
      "Something else is holding a lock on this. Nothing could be tried out, " +
      "so nothing is run — try again when it lets go."
    )
  }
  return null
}

/**
 * The cached answers a committed structure change makes untrue.
 *
 * Built from what the source said changed, never from the SQL that was sent:
 * a node id is the source's, and a browser that took one apart would be
 * reading a promise D21 does not make (D66).
 *
 * `connection` is the honest wider answer for a statement that does not say
 * which node it was about, and it becomes the prefix of every key belonging to
 * this connection.
 */
export function invalidationsFor(
  effect: SchemaEffect | null | undefined,
  connectorId: string
): unknown[][] {
  if (effect === null || effect === undefined) return []
  // Rows and file content are keyed by connection alone, so they are dropped
  // wholesale whatever the scope: a changed column changes every page read
  // from that relation, and the key does not name a relation.
  const keys: unknown[][] = [
    ["rows", connectorId],
    ["content", connectorId],
    ["queries", "metadata", connectorId],
  ]
  if (effect.scope === "connection") {
    return [...keys, ["catalog", connectorId], ["relationModel", connectorId]]
  }
  for (const nodeId of effect.reload_node_ids ?? []) {
    keys.push(["catalog", connectorId, nodeId])
  }
  for (const nodeId of effect.relation_node_ids ?? []) {
    keys.push(["relationModel", connectorId, nodeId])
    // A relation's own children — a schema's list is the parent's, but a node
    // that was renamed or dropped is read from its own branch too.
    keys.push(["catalog", connectorId, nodeId])
  }
  return keys
}
