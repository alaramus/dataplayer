import { describe, expect, it } from "vitest"

import { AGENT_KINDS, AGENT_LOOKS, agentKindOf, readAgentBlock } from "./agent"
import { splitDocument } from "./blocks"

describe("recognising a callout by its fence", () => {
  it("knows every kind it draws", () => {
    for (const kind of AGENT_KINDS) {
      expect(agentKindOf(kind)).toBe(kind)
      expect(AGENT_LOOKS[kind].icon).not.toBe("")
    }
  })

  it("accepts the explicit prefix", () => {
    expect(agentKindOf("callout:risk")).toBe("risk")
  })

  it("leaves an ordinary language alone", () => {
    expect(agentKindOf("python")).toBeNull()
    expect(agentKindOf("callout:python")).toBeNull()
    expect(agentKindOf("")).toBeNull()
  })

  it("becomes its own block, not a listing", () => {
    const blocks = splitDocument("```decision\nDecision: ship it\n```")

    expect(blocks).toEqual([{ type: "agent", kind: "decision", code: "Decision: ship it" }])
  })
})

describe("reading what a callout holds", () => {
  it("takes the leading key lines as fields", () => {
    const content = readAgentBlock("path: src/app.py\naction: inspect\n")

    expect(content.fields).toEqual([
      { key: "path", value: "src/app.py" },
      { key: "action", value: "inspect" },
    ])
    expect(content.body).toBe("")
  })

  it("keeps the rest as the body, Markdown and all", () => {
    const content = readAgentBlock("path: src/app.py\n\nCheck the **boundary** here.")

    expect(content.fields).toEqual([{ key: "path", value: "src/app.py" }])
    expect(content.body).toBe("Check the **boundary** here.")
  })

  it("stops reading fields once prose has started", () => {
    const content = readAgentBlock("Something happened.\nreason: it does not matter here")

    expect(content.fields).toEqual([])
    expect(content.body).toBe("Something happened.\nreason: it does not matter here")
  })

  it("treats a callout with no fields as all body", () => {
    expect(readAgentBlock("  Just a sentence.  ")).toEqual({
      fields: [],
      body: "Just a sentence.",
    })
  })
})
