import { describe, expect, it } from "vitest"

/**
 * The showcase breaks when a component breaks, because it renders the real
 * thing. What it cannot notice on its own is a component that was never added
 * to it — so that is checked here, and the same for the barrel.
 */

const COMPONENT_FILES = import.meta.glob("../../shared/ui/*.vue", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

const SHOWCASE = Object.values(
  import.meta.glob("./UiKitPage.vue", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>
)[0]

const BARREL = Object.values(
  import.meta.glob("../../shared/ui/index.ts", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>
)[0]

const names = Object.keys(COMPONENT_FILES)
  .map((path) => path.split("/").pop()?.replace(".vue", "") ?? "")
  .sort()

describe("the kit showcase", () => {
  it("finds the components to check", () => {
    expect(names.length).toBeGreaterThan(10)
  })

  it.each(names)("demonstrates %s", (name) => {
    expect(SHOWCASE).toContain(`<${name}`)
  })
})

describe("the kit barrel", () => {
  it.each(names)("exports %s", (name) => {
    expect(BARREL).toContain(`export { default as ${name} }`)
  })
})
