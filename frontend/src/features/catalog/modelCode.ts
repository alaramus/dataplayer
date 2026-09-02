/**
 * What a written model can be taken to, when something can take it.
 *
 * One dialect of the three is a website's own language, and that earns a door
 * beside Copy and Save. The rule is here rather than inside the dialog so it
 * can be read and tested on its own, and so a second such dialect is one line
 * rather than a second branch in the markup.
 *
 * The value is the source's, never invented here: this only says what is known
 * about one of them.
 */

export const DBDIAGRAM_URL = "https://dbdiagram.io/d"

const DRAWN_BY: Record<string, { url: string; label: string }> = {
  dbml: { url: DBDIAGRAM_URL, label: "dbdiagram.io" },
}

/** Where this dialect is drawn, or nothing when nowhere is. */
export function drawnBy(dialect: string): { url: string; label: string } | null {
  return DRAWN_BY[dialect] ?? null
}
