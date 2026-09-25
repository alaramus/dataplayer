import { beforeEach, describe, expect, it } from "vitest"
import { defineComponent, effectScope, h, nextTick } from "vue"

import type { ConnectorPublic } from "@/client"
import { leavesOf, makeLeaf, makeSplit, useWorkspace } from "@/shared/workspace"

import { panelSchema, roleOf } from "./panels"
import type { Panel } from "./panels"
import { usePairs } from "./usePairs"

const Stub = defineComponent({ setup: () => () => h("div") })

const catalog = (id: string, connectorId: string, title: string): Panel => ({
  id, kind: "catalog", connectorId, title, adapterType: "file",
})

function build() {
  const scope = effectScope()
  return scope.run(() => {
    const workspace = useWorkspace<Panel>({
      storageKey: "test-pairs",
      panelSchema,
      defaults: () => ({
        tree: makeSplit("root", "row", [
          makeLeaf("sources", ["connectors"], { accepts: "sources", pinned: true }),
          makeLeaf("navigate", ["catalog:f", "catalog:f:copy", "catalog:d"], {
            accepts: "navigate", pinned: true,
          }),
          makeLeaf("work", [], { accepts: "work", pinned: true }),
        ], [20, 30, 50]),
        panels: [
          { id: "connectors", kind: "connectors" },
          catalog("catalog:f", "f", "Files"),
          catalog("catalog:f:copy", "f", "Files"),
          catalog("catalog:d", "d", "Postgres"),
        ],
      }),
      kindOf: roleOf,
      look: (panel) => ({ title: panel.id, icon: "square" }),
      component: () => Stub,
    })
    const opened: string[] = []
    const openCatalog = (connector: ConnectorPublic) => {
      opened.push(connector.id)
      workspace.open(catalog(`catalog:${connector.id}`, connector.id, connector.name))
    }
    return { workspace, pairs: usePairs(workspace, openCatalog), opened }
  })!
}

function inLayout(workspace: ReturnType<typeof build>["workspace"]) {
  return leavesOf(workspace.context.tree.value).flatMap((leaf) => leaf.panels)
}

beforeEach(() => {
  localStorage.clear()
})

describe("making a pair", () => {
  it("only remembers the first catalog, which stays where it was", () => {
    const { workspace, pairs } = build()

    pairs.offer("catalog:f")

    expect(pairs.waiting.value?.title).toBe("Files")
    expect(inLayout(workspace)).toContain("catalog:f")
    expect(workspace.context.detached.value).toEqual([])
  })

  it("refuses a second catalog of the same connection", () => {
    const { workspace, pairs } = build()

    pairs.offer("catalog:f")
    pairs.offer("catalog:f:copy")

    expect(pairs.pairs.value).toEqual([])
    expect(pairs.waiting.value?.panelId).toBe("catalog:f")
    expect(workspace.context.detached.value).toEqual([])
  })

  it("tears both catalogs off into one group when the second arrives", () => {
    const { workspace, pairs } = build()

    pairs.offer("catalog:f")
    pairs.offer("catalog:d")

    const [pair] = pairs.pairs.value
    expect(pair?.left.panelId).toBe("catalog:f")
    expect(pair?.right.panelId).toBe("catalog:d")
    expect(pairs.waiting.value).toBeNull()
    expect(workspace.context.detached.value.map((entry) => [entry.panelId, entry.group]))
      .toEqual([["catalog:f", pair?.id], ["catalog:d", pair?.id]])
    expect(inLayout(workspace)).not.toContain("catalog:f")
  })

  it("chooses the second without a drag, opening its catalog", () => {
    const { pairs, opened } = build()

    pairs.offer("catalog:f")
    pairs.pairWith({ id: "s", name: "SSH" } as ConnectorPublic)

    expect(opened).toEqual(["s"])
    expect(pairs.pairs.value[0]?.right.title).toBe("SSH")
  })

  it("forgets the waiting catalog when it is cancelled or closed", async () => {
    const { workspace, pairs } = build()

    pairs.offer("catalog:f")
    pairs.cancel()
    expect(pairs.waiting.value).toBeNull()

    pairs.offer("catalog:d")
    workspace.context.close("catalog:d")
    await nextTick()
    expect(pairs.waiting.value).toBeNull()
  })
})

describe("an open pair", () => {
  it("swaps its sides", () => {
    const { pairs } = build()
    pairs.offer("catalog:f")
    pairs.offer("catalog:d")

    pairs.swap(pairs.pairs.value[0]!.id)

    expect(pairs.pairs.value[0]?.left.title).toBe("Postgres")
  })

  it("sends both catalogs home when it is taken apart", () => {
    const { workspace, pairs } = build()
    pairs.offer("catalog:f")
    pairs.offer("catalog:d")

    pairs.unpair(pairs.pairs.value[0]!.id)

    expect(pairs.pairs.value).toEqual([])
    expect(workspace.context.detached.value).toEqual([])
    expect(inLayout(workspace)).toEqual(expect.arrayContaining(["catalog:f", "catalog:d"]))
  })

  it("comes apart when one of its catalogs is closed, sending the other home", async () => {
    const { workspace, pairs } = build()
    pairs.offer("catalog:f")
    pairs.offer("catalog:d")

    workspace.context.close("catalog:d")
    await nextTick()

    expect(pairs.pairs.value).toEqual([])
    expect(workspace.context.detached.value).toEqual([])
    expect(inLayout(workspace)).toContain("catalog:f")
  })
})
