export interface SqlToken {
  text: string
  kind: "plain" | "keyword" | "literal" | "comment"
}

const keywords = new Set(
  "CREATE UNLOGGED TABLE INDEX UNIQUE NULLS NOT NULL CONSTRAINT PRIMARY KEY FOREIGN REFERENCES CHECK GENERATED ALWAYS BY DEFAULT AS IDENTITY STORED MATCH SIMPLE FULL ON DELETE UPDATE RESTRICT CASCADE DEFERRABLE INITIALLY DEFERRED IMMEDIATE USING INCLUDE WHERE ASC DESC FIRST LAST COMMENT IS ALTER OWNER TO PARTITION RANGE LIST HASH TABLESPACE COLLATE AND OR IN".split(
    " "
  )
)

/** Presentation only: quoted identifiers and literals never become markup. */
export function sqlTokens(sql: string): SqlToken[] {
  return Array.from(
    sql.matchAll(
      /--[^\n]*|\/\*[\s\S]*?\*\/|'(?:''|[^'])*'|"(?:""|[^"])*"|\b[A-Za-z_][A-Za-z_0-9]*\b|[^A-Za-z_'"/-]+|./g
    ),
    ([text]) => ({
      text,
      kind:
        text.startsWith("--") || text.startsWith("/*")
          ? "comment"
          : text.startsWith("'")
            ? "literal"
            : keywords.has(text.toUpperCase())
              ? "keyword"
              : "plain",
    })
  )
}
