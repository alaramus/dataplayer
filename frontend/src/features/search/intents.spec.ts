import { describe, expect, it, vi } from "vitest"

import type { Hit } from "@/client"

import { INTENTS, openHit, showInCatalog, showsInCatalog } from "./intents"
import type { Openers } from "./intents"
import type { ObjectType } from "./kinds"
import { hit } from "./testing"

function openers(): Openers & Record<string, ReturnType<typeof vi.fn>> {
  return {
    intent: vi.fn(),
    connectionWindow: vi.fn(),
    guidePage: vi.fn(),
    sourceType: vi.fn(),
    savedQuery: vi.fn(),
    pipeline: vi.fn(),
    dashboard: vi.fn(),
    conversation: vi.fn(),
    quickChat: vi.fn(),
    project: vi.fn(),
    service: vi.fn(),
    sshKey: vi.fn(),
    tab: vi.fn(),
    tabGroup: vi.fn(),
    unopenable: vi.fn(),
  }
}

function object(type: ObjectType, id: string, open: Hit["open"] = type): Hit {
  return hit(`object:${type}:${id}`, { target: { kind: "object", object_type: type, object_id: id }, open })
}

const HOW = { float: true }

const TABLE: Hit = hit("node:c1:public.orders:", {
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
    node: {
      kind: "table",
      id: "public.orders",
      name: "orders",
      has_children: false,
      representations: [{ kind: "table", title: "Rows" }],
      describable: true,
    } as never,
  },
  open: "preferred",
})

describe("the open registry", () => {
  it("has an entry for every intent the server can send", () => {
    // The record is typed over the generated union, so a missing entry fails
    // to compile; this says the same at run time for the reader.
    expect(Object.keys(INTENTS).sort()).toEqual(
      [
        "catalog", "preferred", "rows", "structure", "summary", "connection",
        "saved_query", "pipeline", "dashboard", "conversation", "quick_chat", "project",
        "service", "ssh_key", "guide_page", "source_type", "tab", "tab_group",
      ].sort()
    )
  })

  it("opens a switched-on connection on its catalog and a switched-off one on its window", async () => {
    const calls = openers()
    const target = { kind: "connection" as const, connector_id: "c1" }
    await openHit(hit("connection:c1", { target, open: "catalog" }), calls, HOW)
    expect(calls.intent).toHaveBeenCalledWith(
      { connectorId: "c1", view: "catalog", describable: false, representations: [] },
      HOW
    )
    await openHit(hit("connection:c1", { target, open: "connection" }), calls, HOW)
    expect(calls.connectionWindow).toHaveBeenCalledWith("c1")
  })

  it("opens a node in the view it names, as its listing describes it", async () => {
    const calls = openers()
    await openHit(TABLE, calls, HOW)
    expect(calls.intent).toHaveBeenCalledWith(
      {
        connectorId: "c1",
        nodeId: "public.orders",
        view: "preferred",
        title: "orders",
        describable: true,
        representations: [{ kind: "table", title: "Rows" }],
      },
      HOW
    )
  })

  it("opens a node found without its listing on what the pointer says", async () => {
    const calls = openers()
    const bare = { ...TABLE, target: { ...TABLE.target, node: null } as Hit["target"], open: "rows" as const }
    await openHit(bare, calls, HOW)
    expect(calls.intent).toHaveBeenCalledWith(
      expect.objectContaining({ view: "rows", describable: false, representations: [] }),
      HOW
    )
  })

  it("shows a node in its catalog", async () => {
    const calls = openers()
    await openHit({ ...TABLE, open: "catalog" }, calls, HOW)
    expect(calls.intent).toHaveBeenCalledWith(
      expect.objectContaining({ connectorId: "c1", nodeId: "public.orders", view: "catalog", title: "orders" }),
      HOW
    )
  })

  it("turns the guide to a page and opens New connection on a source type", async () => {
    const calls = openers()
    await openHit(hit("guide", { target: { kind: "object", object_type: "guide_page", object_id: "redis" } }), calls, HOW)
    expect(calls.guidePage).toHaveBeenCalledWith("redis")
    await openHit(
      hit("type", { target: { kind: "object", object_type: "source_type", object_id: "postgres" }, open: "source_type" }),
      calls,
      HOW
    )
    expect(calls.sourceType).toHaveBeenCalledWith("postgres")
  })

  it("opens a saved query in the console, a service at the foot and a key in Preferences", async () => {
    const calls = openers()
    await openHit(
      hit("q", { target: { kind: "object", object_type: "saved_query", object_id: "q1" }, title: "Monthly", open: "saved_query" }),
      calls,
      HOW
    )
    expect(calls.savedQuery).toHaveBeenCalledWith("q1", "Monthly", HOW)
    await openHit(hit("s", { target: { kind: "object", object_type: "service", object_id: "s1" }, open: "service" }), calls, HOW)
    expect(calls.service).toHaveBeenCalledWith("s1")
    await openHit(hit("k", { target: { kind: "object", object_type: "ssh_key", object_id: "k1" }, open: "ssh_key" }), calls, HOW)
    expect(calls.sshKey).toHaveBeenCalledWith("k1")
  })

  it("opens every application object where it lives", async () => {
    const calls = openers()
    const cases: [ObjectType, string][] = [
      ["pipeline", "pipeline"],
      ["dashboard", "dashboard"],
      ["conversation", "conversation"],
      ["quick_chat", "quickChat"],
      ["project", "project"],
      ["tab", "tab"],
      ["tab_group", "tabGroup"],
    ]
    for (const [type, opener] of cases) {
      await openHit(object(type, `${type}-1`), calls, HOW)
      expect(calls[opener], type).toHaveBeenCalledExactlyOnceWith(`${type}-1`)
    }
    expect(calls.unopenable).not.toHaveBeenCalled()
  })

  it("refuses an intent whose target is not what it opens, and says so", async () => {
    const calls = openers()
    await openHit(hit("x", { open: "source_type" }), calls, HOW)
    expect(calls.sourceType).not.toHaveBeenCalled()
    const elsewhere = object("pipeline", "p1", "dashboard")
    await openHit(elsewhere, calls, HOW)
    expect(calls.dashboard).not.toHaveBeenCalled()
    await openHit({ ...TABLE, open: "conversation" }, calls, HOW)
    expect(calls.conversation).not.toHaveBeenCalled()
    expect(calls.unopenable).toHaveBeenCalledTimes(3)
    expect(calls.unopenable).toHaveBeenCalledWith(elsewhere)
  })
})

describe("Show in catalog", () => {
  it("is offered on every node and on nothing else", () => {
    expect(showsInCatalog(TABLE)).toBe(true)
    expect(showsInCatalog(hit("connection:c1", { target: { kind: "connection", connector_id: "c1" }, open: "catalog" }))).toBe(false)
    expect(showsInCatalog(object("dashboard", "d1"))).toBe(false)
  })

  it("shows a node in its catalog whatever it opens as", async () => {
    const calls = openers()
    await showInCatalog(TABLE, calls, HOW)
    expect(calls.intent).toHaveBeenCalledWith(
      expect.objectContaining({ connectorId: "c1", nodeId: "public.orders", view: "catalog", title: "orders" }),
      HOW
    )
  })

  it("hands a key its ancestors, for a source with no node path", async () => {
    const calls = openers()
    const key = hit("node:r1:k0:cache:user:1:", {
      target: {
        kind: "node",
        connector_id: "r1",
        node_id: "k0:cache:user:1",
        parent_id: null,
        location: "db0 · cache:user:",
        name: "cache:user:1",
        node_kind: "key",
        sub_key: null,
        ancestors: [
          { node_id: "d0", name: "db0" },
          { node_id: "f0:cache:", name: "cache:" },
          { node_id: "f0:cache:user:", name: "user:" },
        ],
        node: null,
      },
      open: "preferred",
    })
    await showInCatalog(key, calls, HOW)
    expect(calls.intent).toHaveBeenCalledWith(
      expect.objectContaining({
        nodeId: "k0:cache:user:1",
        view: "catalog",
        ancestors: [
          { id: "d0", label: "db0" },
          { id: "f0:cache:", label: "cache:" },
          { id: "f0:cache:user:", label: "user:" },
        ],
      }),
      HOW
    )
  })

  it("says so for a hit that is not a node", async () => {
    const calls = openers()
    const dashboard = object("dashboard", "d1")
    await showInCatalog(dashboard, calls, HOW)
    expect(calls.intent).not.toHaveBeenCalled()
    expect(calls.unopenable).toHaveBeenCalledWith(dashboard)
  })
})
