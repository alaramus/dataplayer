import { describe, expect, it, vi } from "vitest"

import type { ConnectorPublic } from "@/client"

import { openIntentWith } from "./state"
import type { IntentOpeners, OpenIntent } from "./state"

const PG = { id: "c1", name: "local pg", adapter_type: "postgres", enabled: true } as ConnectorPublic

function openers(): IntentOpeners & Record<string, ReturnType<typeof vi.fn>> {
  return {
    openCatalog: vi.fn(),
    openStructure: vi.fn(),
    openSummary: vi.fn(),
    openRepresentation: vi.fn(),
    openRows: vi.fn(),
    reveal: vi.fn(),
  }
}

const NODE: OpenIntent = {
  connectorId: "c1",
  nodeId: "public.orders",
  view: "rows",
  title: "orders",
  describable: true,
  representations: [],
}

describe("an intent turned into a panel (D205)", () => {
  it("opens a connection on its catalog", () => {
    const calls = openers()
    openIntentWith(calls, PG, { connectorId: "c1", view: "catalog", describable: false, representations: [] })
    expect(calls.openCatalog).toHaveBeenCalledWith(PG)
  })

  it("shows a node in its catalog", () => {
    const calls = openers()
    openIntentWith(calls, PG, { ...NODE, view: "catalog" })
    expect(calls.reveal).toHaveBeenCalledWith(PG, { nodeId: "public.orders", label: "orders" })
  })

  it("hands the catalog the node's ancestors, for a source with no node path", () => {
    const calls = openers()
    const ancestors = [{ id: "d0", label: "db0" }, { id: "f0:cache:", label: "cache:" }]
    openIntentWith(calls, PG, { ...NODE, nodeId: "k0:cache:one", title: "cache:one", view: "catalog", ancestors })
    expect(calls.reveal).toHaveBeenCalledWith(PG, { nodeId: "k0:cache:one", label: "cache:one", ancestors })
  })

  it("opens a node in the view it names, as the catalog would", () => {
    const calls = openers()
    openIntentWith(calls, PG, { ...NODE, view: "structure" })
    openIntentWith(calls, PG, { ...NODE, view: "summary" })
    openIntentWith(calls, PG, { ...NODE, containerId: "public" })
    const node = {
      connectorId: "c1",
      nodeId: "public.orders",
      title: "orders",
      connectorName: "local pg",
      adapterType: "postgres",
    }
    expect(calls.openStructure).toHaveBeenCalledWith(node)
    expect(calls.openSummary).toHaveBeenCalledWith(node)
    expect(calls.openRows).toHaveBeenCalledWith({
      ...node,
      describable: true,
      representations: [],
      containerId: "public",
    })
  })

  it("opens the preferred view where the node has one, and its rows where it has none", () => {
    const calls = openers()
    const markdown = { kind: "markdown" as const, title: "Document" }
    openIntentWith(calls, PG, { ...NODE, view: "preferred", representations: [markdown] })
    openIntentWith(calls, PG, { ...NODE, view: "preferred" })
    expect(calls.openRepresentation).toHaveBeenCalledOnce()
    expect(calls.openRows).toHaveBeenCalledOnce()
  })

  it("names a node by its id when the pointer has no title", () => {
    const calls = openers()
    openIntentWith(calls, PG, { ...NODE, view: "structure", title: null })
    expect(calls.openStructure).toHaveBeenCalledWith(expect.objectContaining({ title: "public.orders" }))
  })
})
