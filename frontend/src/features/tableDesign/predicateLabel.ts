import type { DraftColumn, DraftPredicate, DraftTerm } from "./draft"

const operators: Record<DraftTerm["operator"], string> = {
  eq: "=",
  ne: "<>",
  lt: "<",
  lte: "<=",
  gt: ">",
  gte: ">=",
  in: "IN",
  not_in: "NOT IN",
  is_null: "IS NULL",
  is_not_null: "IS NOT NULL",
}

/** A label for the editor, never used as a statement or sent to the source. */
export function predicateLabel(predicate: DraftPredicate, columns: DraftColumn[]): string {
  return predicate.terms
    .map((term) => {
      const name = columns.find((column) => column.id === term.columnId)?.name || "Choose column"
      const head = `${name} ${operators[term.operator]}`
      if (term.operator === "is_null" || term.operator === "is_not_null") return head
      const value = (text: string) =>
        term.valueKind === "text" || term.valueKind === "json"
          ? `'${text.replaceAll("'", "''")}'`
          : text
      return term.operator === "in" || term.operator === "not_in"
        ? `${head} (${term.values.map(value).join(", ")})`
        : `${head} ${value(term.value)}`
    })
    .join(predicate.operator === "and" ? " AND " : " OR ")
}
