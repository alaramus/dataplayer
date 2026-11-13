import { describe, expect, it } from "vitest"

import type { FollowedLinkPublic, Link } from "@/client"

import { followedLinks, followTone, followWords } from "./follow"
import { FOLLOW_MARK, linkEdge } from "./links"

function entry(over: Partial<FollowedLinkPublic> = {}): FollowedLinkPublic {
  return { link_id: "l1", carried: 0, last_at: null, failures: 0, last_error: null, state: "idle", ...over }
}

const link: Link = {
  id: "l1",
  source: { card_id: "a", node_id: "topic:orders" },
  target: { card_id: "b", node_id: "public.orders" },
  kind: "rows_since_last",
  title: "Add new messages to a table",
  runs: "continuous",
}

describe("a pipeline's continuous links while it is on (D315, D362)", () => {
  it("colours a followed line by what its link does now", () => {
    expect(followTone(entry({ state: "carrying" }))).toBe("info")
    expect(followTone(entry({ state: "retrying" }))).toBe("error")
    expect(followTone(entry())).toBeUndefined()
    expect(followTone(undefined)).toBeUndefined()
  })

  it("marks a followed link before its title, and its tone wins over the last run while following", () => {
    const edge = linkEdge(link, undefined, { link_id: "l1", outcome: "done" }, "info")
    expect(edge.label).toBe(`${FOLLOW_MARK} Add new messages to a table`)
    expect(edge.tone).toBe("info")
    // Following, and idle: the plain line, not the last run's colour.
    expect(linkEdge(link, undefined, { link_id: "l1", outcome: "done" }, null).tone).toBeUndefined()
    // Not following: the last run's colour.
    expect(linkEdge(link, undefined, { link_id: "l1", outcome: "done" }).tone).toBe("success")
    expect(linkEdge({ ...link, runs: "scheduled" }).label).toBe("Add new messages to a table")
  })

  it("says what a followed link did", () => {
    const at = () => "12:00"
    expect(followWords(undefined, at)).toBe("Following: nothing new yet")
    expect(followWords(entry({ carried: 5, last_at: "2026-11-08T12:00:00Z" }), at)).toBe(
      "Following: messages carried: 5, the last at 12:00"
    )
    expect(followWords(entry({ state: "retrying", failures: 2, last_error: "Kafka is away" }), at)).toBe(
      "Trying again (failures in a row: 2): Kafka is away"
    )
  })

  it("keys the following's entries by link", () => {
    const state = { on: true, status: { kind: "on" as const }, follow: { running: true, links: [entry()] } }
    expect(followedLinks(state).get("l1")?.carried).toBe(0)
    expect(followedLinks(undefined).size).toBe(0)
  })
})
