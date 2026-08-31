import { describe, expect, it, vi } from "vitest"

import type { CatalogNode } from "@/features/catalog/nodes"

import { resolveRelativeTarget } from "./relative"

function directory(id: string, name: string): CatalogNode {
  return { kind: "directory", id, name, has_children: true, representations: [] }
}

function file(id: string, name: string, kind: "markdown" | "image" = "markdown"): CatalogNode {
  return {
    kind: "file",
    id,
    name,
    size_bytes: 10,
    representations: [{ kind, title: kind === "image" ? "View image" : "View as document" }],
  }
}

describe("relative document targets", () => {
  it("walks source-issued parents and children without constructing an id", async () => {
    const docs = directory("opaque-docs", "docs")
    const chapter = directory("opaque-chapter", "chapter")
    const guide = file("opaque-guide", "guide.md")
    const picture = file("opaque-picture", "diagram one.png", "image")
    const loadPath = vi.fn().mockResolvedValue([docs, chapter, guide])
    const loadChildren = vi
      .fn()
      .mockImplementation(async (_connector: string, parent: string | null) => {
        if (parent === "opaque-docs") return [chapter, picture]
        return []
      })

    const result = await resolveRelativeTarget(
      "c1",
      "opaque-guide",
      "../diagram%20one.png#large",
      loadPath,
      loadChildren
    )

    expect(result).toEqual({ node: picture, fragment: "large" })
    expect(loadChildren).toHaveBeenCalledWith("c1", "opaque-docs")
    expect(loadChildren.mock.calls.flat()).not.toContain("docs/diagram one.png")
  })

  it("keeps an empty path on the current source-issued node", async () => {
    const guide = file("not-a-path", "guide.md")

    await expect(
      resolveRelativeTarget(
        "c1",
        guide.id,
        "?mode=read#details",
        async () => [guide],
        async () => []
      )
    ).resolves.toEqual({ node: guide, fragment: "details" })
  })

  it("refuses to walk above the connector root", async () => {
    const guide = file("opaque-guide", "guide.md")

    await expect(
      resolveRelativeTarget(
        "c1",
        guide.id,
        "../outside.md",
        async () => [guide],
        async () => []
      )
    ).rejects.toThrow("leaves the connection root")
  })

  it("names a missing target instead of returning a guessed path", async () => {
    const docs = directory("opaque-docs", "docs")
    const guide = file("opaque-guide", "guide.md")

    await expect(
      resolveRelativeTarget(
        "c1",
        guide.id,
        "missing.md",
        async () => [docs, guide],
        async () => []
      )
    ).rejects.toThrow("No node named missing.md")
  })
})
