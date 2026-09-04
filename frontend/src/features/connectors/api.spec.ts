import { QueryClient } from "@tanstack/vue-query"
import { describe, expect, it } from "vitest"

import type { ConnectorsPublic } from "@/client"
import { grantsKey } from "@/features/connectors/grants"
import { unlockKey } from "@/features/queries/runs"

import { connectorNameOf, connectorsKey } from "./api"

const list = (name: string): ConnectorsPublic => ({
  count: 1,
  data: [
    {
      id: "c1",
      name,
      adapter_type: "postgres",
      config: {},
      enabled: true,
      access: "own",
      execution_policy: "confirm_writes",
    },
  ],
})

describe("the name a connection has now", () => {
  it("is read from the list by id, and is nothing for a connection that is gone", () => {
    expect(connectorNameOf(list("renamed"), "c1")).toBe("renamed")
    expect(connectorNameOf(list("renamed"), "c2")).toBeNull()
    expect(connectorNameOf(list("renamed"), null)).toBeNull()
    expect(connectorNameOf(undefined, "c1")).toBeNull()
  })
})

describe("what a change to a connection invalidates", () => {
  it("drops everything cached about that connection, not only the list", async () => {
    // Whether writing is open on a connection is made of the owner's policy
    // and this person's level — both facts about the connection, both stale
    // the moment it is edited. It was cached under `queries` once, so an open
    // console went on judging a connection by the policy it used to have.
    const client = new QueryClient()
    client.setQueryData(unlockKey("c1"), { unlocked: true })
    client.setQueryData(grantsKey("c1"), { data: [], count: 0 })

    await client.invalidateQueries({ queryKey: connectorsKey })

    expect(client.getQueryState(unlockKey("c1"))?.isInvalidated).toBe(true)
    expect(client.getQueryState(grantsKey("c1"))?.isInvalidated).toBe(true)
  })
})
