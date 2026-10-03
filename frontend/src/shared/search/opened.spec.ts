import { beforeEach, describe, expect, it } from "vitest"

import type { Hit } from "@/client"
import { serverStorageKey } from "@/shared/servers/context"

import {
  forgetOpened,
  openedTarget,
  parseOpened,
  readOpened,
  RECENTLY_OPENED_LIMIT,
  rememberOpened,
} from "./opened"

function objectHit(id: string): Hit {
  return {
    key: `object:guide_page:${id}`,
    target: { kind: "object", object_type: "guide_page", object_id: id },
    title: id,
    detail: null,
    facts: { kind: "guide_page", changed_at: null, owner: null, switched_off: false },
    match: { field: "name", match_class: "prefix", line: null, excerpt: [{ text: id, hit: true }] },
    access: null,
    open: "guide_page",
    via: "live",
    as_of: null,
  }
}

function nodeHit(over: Partial<Extract<Hit["target"], { kind: "node" }>> = {}): Hit {
  return {
    ...objectHit("x"),
    key: "node:c1:public.orders:",
    target: {
      kind: "node",
      connector_id: "c1",
      node_id: "public.orders",
      parent_id: "public",
      location: "public",
      name: "orders",
      node_kind: "table",
      sub_key: null,
      ancestors: null,
      node: null,
      ...over,
    },
    open: "preferred",
  }
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
})

describe("what was opened from the search", () => {
  it("keeps the target only: a node's ids, name and kind, nothing it was found by", () => {
    expect(openedTarget(nodeHit())).toEqual({
      kind: "node",
      connector_id: "c1",
      node_id: "public.orders",
      name: "orders",
      node_kind: "table",
    })
    expect(openedTarget(objectHit("start"))).toEqual({ kind: "object", object_type: "guide_page", object_id: "start" })
  })

  it("keeps the last fifty, newest first, a thing opened again moved to the front", () => {
    for (let index = 0; index < 55; index++) rememberOpened("u1", objectHit(`page-${String(index)}`))
    rememberOpened("u1", objectHit("page-10"))
    const kept = readOpened("u1")
    expect(kept).toHaveLength(RECENTLY_OPENED_LIMIT)
    expect(kept.slice(0, 2).map((one) => one.object_id)).toEqual(["page-10", "page-54"])
    expect(kept.filter((one) => one.object_id === "page-10")).toHaveLength(1)
  })

  it("lives in local storage per person and server, and is emptied for that person on sign-out", () => {
    rememberOpened("u1", objectHit("start"))
    rememberOpened("u2", objectHit("other"))
    expect(localStorage.getItem(serverStorageKey("dp.search.opened:u1"))).not.toBeNull()
    expect(readOpened("u1").map((one) => one.object_id)).toEqual(["start"])
    forgetOpened("u1")
    expect(readOpened("u1")).toEqual([])
    expect(readOpened("u2").map((one) => one.object_id)).toEqual(["other"])
  })

  it("keeps nothing for nobody", () => {
    rememberOpened(undefined, objectHit("start"))
    expect(localStorage.length).toBe(0)
    expect(readOpened(null)).toEqual([])
  })

  it("does not keep a target the server would refuse, and cuts a long name", () => {
    rememberOpened("u1", nodeHit({ node_kind: "k".repeat(65) }))
    expect(readOpened("u1")).toEqual([])
    expect(openedTarget(nodeHit({ name: "n".repeat(1200) }))?.name).toHaveLength(1000)
  })

  it("reads a damaged value entry by entry rather than failing", () => {
    expect(parseOpened("{not json")).toEqual([])
    expect(parseOpened('{"a": 1}')).toEqual([])
    expect(
      parseOpened(
        JSON.stringify([
          { kind: "connection", connector_id: "c1" },
          { kind: "connection" },
          { kind: "object", object_type: "nonsense", object_id: "x" },
          { kind: "node", connector_id: "c1", node_id: "n", name: "n", node_kind: "table", extra: 1 },
          { kind: "connection", connector_id: "c1" },
          3,
        ])
      )
    ).toEqual([
      { kind: "connection", connector_id: "c1" },
      { kind: "node", connector_id: "c1", node_id: "n", name: "n", node_kind: "table" },
    ])
  })
})
