import { describe, expect, it } from "vitest"

import { splitStreamingDocument } from "./streaming"

describe("streaming Markdown", () => {
  it("does not hand an open rich fence to its renderer", () => {
    expect(splitStreamingDocument("Before\n```echarts\n{x: 1}")).toEqual([
      { type: "prose", content: "Before" },
      { type: "pending-fence", language: "echarts" },
    ])
  })

  it("renders the rich block after its fence closes", () => {
    expect(splitStreamingDocument("```echarts\n{}\n```")).toEqual([
      { type: "echarts", code: "{}" },
    ])
  })
})
