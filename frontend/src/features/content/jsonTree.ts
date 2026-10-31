import type { DocumentItem } from "@/client"

/** One value of a JSON tree, as the server sends it (`JsonValue`). */
export type JsonValue = NonNullable<DocumentItem["value"]>

/**
 * How a JSON tree is read out, as plain functions (D295).
 *
 * A document arrives in relaxed Extended JSON, where a value JSON has no word
 * for is an object of one `$`-named field: `{"$oid": "65…"}`. Drawn as an
 * object it reads as noise, so it is drawn as the one value it is, with the
 * BSON type it names — the way `mongosh` and Compass show it.
 */

export type TreeScalar = {
  /** What the value is: a JSON kind, or the BSON type a wrapper names. */
  type: string
  text: string
  /** How it is coloured: as a string, a number, a word, or a typed value. */
  tone: "string" | "number" | "word" | "typed"
}

const WRAPPERS: Record<string, string> = {
  $oid: "ObjectId",
  $date: "Date",
  $numberDecimal: "Decimal128",
  $numberLong: "Int64",
  $numberInt: "Int32",
  $numberDouble: "Double",
  $uuid: "UUID",
  $binary: "Binary",
  $regularExpression: "RegExp",
  $timestamp: "Timestamp",
  $minKey: "MinKey",
  $maxKey: "MaxKey",
  $symbol: "Symbol",
  $code: "Code",
}

function field(value: JsonValue, name: string): JsonValue | undefined {
  return value.kind === "object" ? value.entries.find((entry) => entry.name === name)?.value : undefined
}

function plain(value: JsonValue | undefined): string {
  if (value === undefined) return ""
  if (value.kind === "array") return `[${String(value.items.length)}]`
  if (value.kind === "object") {
    // A date past 9999 is `{"$date": {"$numberLong": "…"}}`: one wrapper in another.
    const inner = typedScalar(value)
    return inner === null ? "{…}" : inner.text
  }
  return value.value ?? "null"
}

/** The value a one-field `$` object stands for, or null for any other value. */
export function typedScalar(value: JsonValue): TreeScalar | null {
  if (value.kind !== "object" || value.entries.length !== 1) return null
  const [{ name, value: inner }] = value.entries as [{ name: string; value: JsonValue }]
  const type = WRAPPERS[name]
  if (type === undefined) return null
  if (name === "$binary") {
    const subtype = plain(field(inner, "subType"))
    return { type: `${type}(${subtype})`, text: plain(field(inner, "base64")), tone: "typed" }
  }
  if (name === "$regularExpression") {
    return { type, text: `/${plain(field(inner, "pattern"))}/${plain(field(inner, "options"))}`, tone: "typed" }
  }
  if (name === "$timestamp") {
    return { type, text: `${plain(field(inner, "t"))}, ${plain(field(inner, "i"))}`, tone: "typed" }
  }
  if (name === "$minKey" || name === "$maxKey") return { type, text: type, tone: "typed" }
  return { type, text: plain(inner), tone: "typed" }
}

/** A scalar of JSON itself, or a typed one; null for an object or an array to open. */
export function scalarOf(value: JsonValue): TreeScalar | null {
  switch (value.kind) {
    case "null":
      return { type: "null", text: "null", tone: "word" }
    case "boolean":
      return { type: "boolean", text: value.value ?? "", tone: "word" }
    case "number":
      return { type: "number", text: value.value ?? "", tone: "number" }
    case "string":
      return { type: "string", text: JSON.stringify(value.value ?? ""), tone: "string" }
    case "array":
      return null
    case "object":
      return typedScalar(value)
  }
}

/** The children of an object or an array, named by key or by position. */
export function childrenOf(value: JsonValue): { name: string; value: JsonValue }[] {
  if (value.kind === "array") return value.items.map((item, index) => ({ name: String(index), value: item }))
  if (value.kind === "object") return value.entries
  return []
}

/** What a closed object or array says about itself: how much is inside. */
export function closedSummary(value: JsonValue): string {
  if (value.kind === "array") return `[ ${String(value.items.length)} ]`
  if (value.kind === "object") return `{ ${String(value.entries.length)} }`
  return ""
}

/** The `_id` a document is known by, as one line. */
export function documentId(value: JsonValue | null | undefined): string {
  if (value == null) return ""
  const id = field(value, "_id")
  if (id === undefined) return ""
  const scalar = scalarOf(id)
  return scalar === null ? closedSummary(id) : scalar.text
}
