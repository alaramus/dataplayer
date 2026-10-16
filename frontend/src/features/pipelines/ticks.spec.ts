import { describe, expect, it } from "vitest"

import type { CardRow } from "@/client"
import { toListNodes } from "@/features/catalog/nodes"
import type { CatalogNode } from "@/features/catalog/nodes"

import { isTicked, MAX_CARD_ROWS, ticked, tickedAll, tickedNode, tooMany, topRow, whereOf } from "./ticks"

function table(name: string): CatalogNode {
  return {
    kind: "table",
    id: `sales.${name}`,
    name,
    has_children: false,
    representations: [{ kind: "table" }],
  } as CatalogNode
}

const [orders, customers] = toListNodes([table("orders"), table("customers")])

describe("what a card's window ticks", () => {
  it("keeps a ticked node as a row that says where it lives", () => {
    const rows = tickedNode([], orders!, ["sales"], true)

    expect(rows).toEqual([{ node_id: "sales.orders", label: "orders", kind: "table", trail: ["sales"] }])
    expect(isTicked(rows as CardRow[], "sales.orders")).toBe(true)
    expect(whereOf((rows as CardRow[])[0]!)).toBe("sales")
  })

  it("ticks the top of a connection apart from any node", () => {
    const rows = ticked([], topRow("Files"), true) as CardRow[]

    expect(rows).toEqual([{ node_id: null, label: "Files", kind: null, trail: [] }])
    expect(isTicked(rows, null)).toBe(true)
    expect(isTicked(rows, "top")).toBe(false)
    expect(ticked(rows, topRow("Files"), false)).toEqual([])
  })

  it("keeps ticks made on another level when this one is ticked or cleared", () => {
    const elsewhere: CardRow = { node_id: "public.people", label: "people", kind: "table", trail: ["public"] }
    const already = tickedNode([elsewhere], customers!, ["sales"], true) as CardRow[]

    const all = tickedAll(already, [orders!, customers!], ["sales"], true) as CardRow[]
    expect(all.map((row) => row.node_id)).toEqual(["public.people", "sales.customers", "sales.orders"])

    expect(tickedAll(all, [orders!, customers!], ["sales"], false)).toEqual([elsewhere])
  })

  it("stops at the bound of a card rather than letting the save be refused", () => {
    const full: CardRow[] = Array.from({ length: MAX_CARD_ROWS }, (_, n) => ({
      node_id: `n${String(n)}`, label: `n${String(n)}`, kind: "file", trail: [],
    }))

    expect(tickedNode(full, orders!, ["sales"], true)).toBe(tooMany())
    expect(tickedAll(full.slice(1), [orders!, customers!], ["sales"], true)).toBe(tooMany())
    expect(tickedNode(full, orders!, ["sales"], false)).toEqual(full)
  })
})
