import type { PreparedScript, QueryMetadata, QueryProfile } from "@/client"

/**
 * What the editor offers, and what it dares say is wrong.
 *
 * Plain data in, plain data out, so both rules can be tested without an editor.
 * Both are conservative on purpose (D65): completion offers what the source has
 * said it has, and a mark appears only where this application actually knows
 * something — limited metadata produces a status, never a red line under a
 * relation that exists.
 */

/** One thing the editor may offer to write. */
export interface Suggestion {
  label: string
  /** What kind of thing it is, shown beside the word. */
  detail: string
  kind: "schema" | "relation" | "column" | "parameter"
}

/**
 * The relation a bare name would mean, for the schemas in context.
 *
 * A source with no schemas answers with an empty one — the file source names
 * its relations by node id and has no schemas at all (D77) — and a name with
 * nothing in front of it is the name itself, not a leading dot.
 */
function qualified(schema: string, name: string): string {
  return schema === "" ? name : `${schema}.${name}`
}

/** How this source spells a named parameter, taken from what it said. */
export function parameterPrefix(
  syntax: QueryProfile["parameter_syntax"] | undefined
): string {
  return syntax === "named_dollar" ? "$" : ":"
}

/**
 * Everything the editor may offer, from what the source has told it.
 *
 * Relations in the current context are offered by their bare name as well as
 * qualified, because that is how somebody writes them; a name that appears in
 * two schemas keeps only its qualified form, since offering an ambiguous bare
 * word would suggest something the server would refuse.
 */
export function suggestions(
  metadata: QueryMetadata | undefined,
  script: PreparedScript | null,
  prefix = ":"
): Suggestion[] {
  const found: Suggestion[] = []
  const seenBare = new Map<string, number>()
  for (const relation of metadata?.relations ?? []) {
    seenBare.set(relation.name, (seenBare.get(relation.name) ?? 0) + 1)
  }
  for (const schema of metadata?.schemas ?? []) {
    found.push({ label: schema, detail: "schema", kind: "schema" })
  }
  for (const relation of metadata?.relations ?? []) {
    found.push({
      label: qualified(relation.schema_name, relation.name),
      detail: relation.kind.replace("_", " "),
      kind: "relation",
    })
    if (seenBare.get(relation.name) === 1 && relation.schema_name !== "") {
      found.push({
        label: relation.name,
        detail: `${relation.kind.replace("_", " ")} in ${relation.schema_name}`,
        kind: "relation",
      })
    }
  }
  const columns = new Map<string, string>()
  for (const [relation, list] of Object.entries(metadata?.columns ?? {})) {
    for (const column of list) {
      if (!columns.has(column.name)) {
        columns.set(column.name, `${column.type_sql} · ${relation}`)
      }
    }
  }
  for (const [name, detail] of columns) {
    found.push({ label: name, detail, kind: "column" })
  }
  for (const parameter of script?.parameters ?? []) {
    found.push({
      label: `${prefix}${parameter}`,
      detail: "parameter",
      kind: "parameter",
    })
  }
  return found
}

/** The relations whose columns are worth asking the source for. */
export function relationsInUse(script: PreparedScript | null): string[] {
  const named = new Set<string>()
  for (const statement of script?.statements ?? []) {
    for (const target of statement.targets ?? []) named.add(target)
  }
  return [...named]
}

/**
 * The schemas the text itself names.
 *
 * D65: another schema arrives when something is qualified with it. A console
 * asks for what somebody has written, not for the whole database.
 */
export function schemasInUse(script: PreparedScript | null): string[] {
  const named = new Set<string>()
  for (const target of relationsInUse(script)) {
    if (target.includes(".")) named.add(target.slice(0, target.indexOf(".")))
  }
  return [...named]
}

/** One mark in the editor, in the shape CodeMirror's linter takes. */
export interface Mark {
  from: number
  to: number
  severity: "warning" | "error"
  message: string
}

/**
 * What is worth marking, and nothing else.
 *
 * `unknown` is a warning about this application rather than about the SQL: the
 * dialect module has not learnt the form. A relation is marked only when the
 * metadata is complete and the schema it names is one the source listed —
 * an alias, a CTE or a partial answer is left alone.
 */
export function marks(
  script: PreparedScript | null,
  metadata: QueryMetadata | undefined
): Mark[] {
  if (script === null) return []
  const found: Mark[] = []
  for (const statement of script.statements) {
    if (statement.kind === "unknown") {
      found.push({
        from: statement.start,
        to: statement.end,
        severity: "warning",
        message: "This statement could not be read, and will not be run",
      })
      continue
    }
    if (statement.kind !== "read") {
      found.push({
        from: statement.start,
        to: statement.end,
        severity: "warning",
        message: `A ${statement.kind} statement cannot run in a read`,
      })
      continue
    }
    if (metadata === undefined || !metadata.complete) continue
    const schemas = new Set(metadata.schemas)
    const known = new Set(
      (metadata.relations ?? []).map((relation) =>
        qualified(relation.schema_name, relation.name)
      )
    )
    for (const target of statement.targets ?? []) {
      // Only a qualified name is ever marked. A bare one may be a CTE, a
      // sub-query's alias or a relation of a schema this editor has not asked
      // about, and a warning under any of those would be this application
      // being wrong out loud.
      if (!target.includes(".")) continue
      const schema = target.slice(0, target.indexOf("."))
      const name = target.slice(target.indexOf(".") + 1)
      if (!schemas.has(schema)) continue
      if (!known.has(target)) {
        found.push({
          from: statement.start,
          to: statement.end,
          severity: "warning",
          message: `${schema} has nothing called ${name}`,
        })
      }
    }
  }
  return found
}

/** What the console says about how much it knows, or nothing at all. */
export function metadataStatus(metadata: QueryMetadata | undefined): string {
  if (metadata === undefined) return "Reading what this connection holds…"
  if (!metadata.complete) {
    return "This connection has more relations than are offered here"
  }
  return ""
}
