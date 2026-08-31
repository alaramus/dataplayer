import { describe, expect, it } from "vitest"

import { createHtmlFileName, createRenderedHtml } from "./export"

describe("rendered document export", () => {
  it("removes controls and search decoration and embeds a local image", async () => {
    const root = document.createElement("article")
    root.className = "markdown-panel__document"
    root.innerHTML = [
      '<h1 tabindex="-1">Guide</h1>',
      '<p><mark data-search-highlight class="markdown-search-active">found</mark></p>',
      "<span data-export-exclude><button>Copy</button></span>",
      '<img src="/api/v1/connectors/content-files/ticket" data-relative-reference="diagram.png" alt="diagram">',
    ].join("")
    document.body.append(root)

    const html = await createRenderedHtml(root, "A <guide>", async () => ({
      ok: true,
      blob: async () => new Blob(["image"], { type: "image/png" }),
    }))

    expect(html).toContain("A &lt;guide&gt;")
    expect(html).toContain("data:image/png;base64,")
    expect(html).not.toContain("data-search-highlight")
    expect(html).not.toContain("data-relative-reference")
    expect(html).not.toContain("Copy")
    expect(html).not.toContain('tabindex="-1"')
    expect(html).not.toContain("<script")
    root.remove()
  })

  it("derives an HTML name from either Markdown suffix", () => {
    expect(createHtmlFileName("guide.markdown")).toBe("guide.html")
    expect(createHtmlFileName("notes.md")).toBe("notes.html")
  })
})
