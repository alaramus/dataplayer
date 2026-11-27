import { describe, expect, it } from "vitest"

import type { GuidePageInfo, Hit } from "@/client"
import { hit } from "@/features/search/testing"

import { foundPages, groupedContents } from "./contents"

const page = (key: string, title: string, section: GuidePageInfo["section"]): GuidePageInfo =>
  ({ key, title, section })

describe("groupedContents", () => {
  it("puts the pages under their sections in the server's order", () => {
    const groups = groupedContents([
      page("overview", "DataPlayer at a glance", "application"),
      page("connections", "Connections", "application"),
      page("source-mysql", "MySQL", "sources"),
      page("source-redis", "Redis", "sources"),
    ])

    expect(groups.map((group) => group.section)).toEqual(["application", "sources"])
    expect(groups[0]?.pages.map((one) => one.key)).toEqual(["overview", "connections"])
    expect(groups[1]?.pages.map((one) => one.key)).toEqual(["source-mysql", "source-redis"])
  })

  it("is nothing for no pages", () => {
    expect(groupedContents([])).toEqual([])
  })
})

describe("foundPages", () => {
  it("keeps the guide's pages in the order found, with where the words are", () => {
    const body: Hit = hit("source-redis", {
      title: "Redis",
      match: {
        field: "body",
        match_class: "text",
        line: null,
        excerpt: [{ text: "keys and ", hit: false }, { text: "streams", hit: true }],
      },
    })
    const title: Hit = hit("pipelines", { title: "Pipelines" })
    const elsewhere: Hit = hit("c1", { target: { kind: "connection", connector_id: "c1" } })

    expect(foundPages([title, elsewhere, body])).toEqual([
      { key: "pipelines", title: "Pipelines", excerpt: [] },
      { key: "source-redis", title: "Redis", excerpt: body.match.excerpt },
    ])
  })
})
