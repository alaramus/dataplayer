import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"

import { describe, expect, it } from "vitest"

/**
 * A token spent is a token declared.
 *
 * `var(--dp-radius)` in a dialog and `var(--dp-danger-text, #d32f2f)` in the
 * highlighter were both found by the audit of 2026-09-19: the first is a
 * declaration the browser drops in silence, the second a literal colour
 * wearing a token's name. Neither the colour nor the spacing test sees them,
 * because both read what a value looks like rather than whether it exists.
 *
 * Vite hands back an empty string for a `.css` file, so the files that declare
 * the tokens are read from the disk instead. A path is relative to `frontend/`,
 * where vitest runs.
 */
const DECLARATION = /["']?(--dp-[a-z0-9-]+)["']?\s*:/g
/* `var(--dp-chart-${accentIndex(node)})` names a family, not a token. */
const COMPOSED = /var\(\s*(--dp-[a-z0-9-]+)\$\{/g
const USE = /var\(\s*(--dp-[a-z0-9-]+)/g

function sources(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return entry.name === "client" ? [] : sources(path)
    // A test names a broken token to explain itself, this one included.
    if (entry.name.endsWith(".spec.ts")) return []
    return /\.(vue|ts|css)$/.test(entry.name) ? [path.replace(/\\/g, "/")] : []
  })
}

const files = sources("src").map((path) => ({ path, text: readFileSync(path, "utf-8") }))

const declared = new Set(
  files.flatMap((file) => [...file.text.matchAll(DECLARATION)].map((match) => match[1]))
)
const families = [
  ...new Set(
    files.flatMap((file) => [...file.text.matchAll(COMPOSED)].map((match) => match[1] as string))
  ),
]
const spent = files.flatMap((file) =>
  [...file.text.matchAll(USE)].map((match) => ({ path: file.path, token: match[1] as string }))
)

describe("the design tokens", () => {
  it("are read from the files that declare them", () => {
    // Read through Vite this would be an empty string, and everything below it
    // vacuous.
    expect(readFileSync("src/shared/ui/metrics.css", "utf-8")).toContain("--dp-space-1")
    expect(declared.size).toBeGreaterThan(50)
    expect(spent.length).toBeGreaterThan(100)
  })

  it("are declared wherever one is spent", () => {
    const missing = spent.filter(
      (use) =>
        !declared.has(use.token) && !families.some((family) => use.token.startsWith(family))
    )

    expect(missing.map((use) => `${use.path}: var(${use.token})`)).toEqual([])
  })
})
