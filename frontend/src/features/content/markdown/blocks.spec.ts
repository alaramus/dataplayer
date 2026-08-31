import { describe, expect, it } from "vitest"

import { MAX_RICH_BLOCK_CHARS, splitDocument } from "./blocks"

describe("splitting a document at its fences", () => {
  it("keeps prose between fences and never hands a diagram to the parser", () => {
    const blocks = splitDocument(
      ["Before.", "", "```mermaid", "graph TD;", "  a-->b;", "```", "", "After."].join("\n")
    )

    expect(blocks).toEqual([
      { type: "prose", content: "Before.\n" },
      { type: "mermaid", code: "graph TD;\n  a-->b;" },
      { type: "prose", content: "\nAfter." },
    ])
  })

  it("tells the rich languages apart from ordinary code", () => {
    const blocks = splitDocument(
      [
        "```echarts",
        "{}",
        "```",
        "```svg",
        "<svg />",
        "```",
        "```python",
        "x = 1",
        "```",
        "```",
        "plain",
        "```",
      ].join("\n")
    )

    expect(blocks.map((block) => block.type)).toEqual(["echarts", "svg", "code", "code"])
    expect(blocks[2]).toEqual({ type: "code", language: "python", code: "x = 1" })
    expect(blocks[3]).toEqual({ type: "code", language: "", code: "plain" })
  })

  it("reads the info string case-insensitively and ignores what follows it", () => {
    const blocks = splitDocument("```Mermaid  title=one\ngraph TD;\n```")

    expect(blocks).toEqual([{ type: "mermaid", code: "graph TD;" }])
  })

  it("closes only on a fence at least as long as the one that opened", () => {
    const blocks = splitDocument("````code\n```\nstill inside\n````\nout")

    expect(blocks).toEqual([
      { type: "code", language: "code", code: "```\nstill inside" },
      { type: "prose", content: "out" },
    ])
  })

  it("refuses to draw a fence over the block ceiling", () => {
    const blocks = splitDocument(
      `\`\`\`mermaid\n${"x".repeat(MAX_RICH_BLOCK_CHARS + 1)}\n\`\`\``
    )

    expect(blocks).toEqual([{ type: "oversized", language: "mermaid" }])
  })

  it("shows a fence cut by the document ceiling as the text it is", () => {
    const blocks = splitDocument("```mermaid\ngraph TD;\n  a--")

    expect(blocks).toEqual([{ type: "code", language: "mermaid", code: "graph TD;\n  a--" }])
  })

  it("drops prose that is only whitespace", () => {
    expect(splitDocument("\n\n   \n")).toEqual([])
  })
})
