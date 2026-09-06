import { describe, expect, it } from "vitest"

import { sqlTokens } from "./sqlTokens"

describe("SQL presentation", () => {
  it("preserves the server script, including quoted keywords and markup", () => {
    const sql = `CREATE TABLE "WHERE" ("a""b" text DEFAULT '<script>''CREATE</script>');\n-- NOT NULL\n/* WHERE */`
    const tokens = sqlTokens(sql)
    expect(tokens.map((token) => token.text).join("")).toBe(sql)
    expect(tokens.find((token) => token.text === '"WHERE"')?.kind).toBe("plain")
    expect(tokens.find((token) => token.text.startsWith("'<script>"))?.kind).toBe("literal")
    expect(tokens.filter((token) => token.kind === "comment")).toHaveLength(2)
  })
})
