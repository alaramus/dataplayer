import { QueryClient } from "@tanstack/vue-query"
import { describe, expect, it } from "vitest"

import type { AdapterTypeInfo, ConnectorsPublic } from "@/client"
import { grantsKey } from "@/features/connectors/grants"
import { sourceFeaturesKey } from "@/features/connectors/features"
import { unlockKey } from "@/features/queries/runs"

import {
  connectionKeepsAnswers,
  connectorColorOf,
  connectorNameOf,
  connectorsKey,
} from "./api"

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

describe("the colour a connection was given", () => {
  it("is read the same way, and is nothing where none was chosen", () => {
    const coloured = list("kept")
    coloured.data[0]!.tab_color = "#246abc"
    expect(connectorColorOf(coloured, "c1")).toBe("#246abc")
    expect(connectorColorOf(coloured, "c2")).toBeNull()
    expect(connectorColorOf(coloured, null)).toBeNull()
    expect(connectorColorOf(undefined, "c1")).toBeNull()
    expect(connectorColorOf(list("plain"), "c1")).toBeNull()
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
    client.setQueryData(sourceFeaturesKey("c1"), { features: [] })

    await client.invalidateQueries({ queryKey: connectorsKey })

    expect(client.getQueryState(unlockKey("c1"))?.isInvalidated).toBe(true)
    expect(client.getQueryState(grantsKey("c1"))?.isInvalidated).toBe(true)
    expect(client.getQueryState(sourceFeaturesKey("c1"))?.isInvalidated).toBe(true)
  })
})


const adapterType = (
  overrides: Partial<AdapterTypeInfo> = {}
): AdapterTypeInfo => ({
  name: "postgres",
  title: "PostgreSQL",
  category: "sql",
  category_title: "SQL Databases",
  catalog_shape: "levels",
  description: "Relational database.",
  capabilities: [],
  cache_windows: { catalog: 30, fetch: 10 },
  options_schema: {},
  ...overrides,
})

const TYPES = [adapterType(), adapterType({ name: "file", cache_windows: null })]

describe("whether an answer from a connection could be older than the read", () => {
  it("is yes for a source that caches and a connection that did not refuse", () => {
    expect(connectionKeepsAnswers(list("kept"), TYPES, "c1")).toBe(true)
  })

  it("is no for a source that never opted into caching", () => {
    // A file source is read live whatever its owner typed into the form, so a
    // badge over it would promise a cache that is not there (D105).
    const files = list("files")
    files.data[0]!.adapter_type = "file"
    expect(connectionKeepsAnswers(files, TYPES, "c1")).toBe(false)
  })

  it("is no for an owner who chose to keep nothing", () => {
    const live = list("live")
    live.data[0]!.cache_ttl_seconds = 0
    expect(connectionKeepsAnswers(live, TYPES, "c1")).toBe(false)
  })

  it("is no while the lists have not arrived, and for a connection that is gone", () => {
    // A badge that appears late is easier to read than one that appears and
    // then goes away.
    expect(connectionKeepsAnswers(undefined, TYPES, "c1")).toBe(false)
    expect(connectionKeepsAnswers(list("kept"), undefined, "c1")).toBe(false)
    expect(connectionKeepsAnswers(list("kept"), TYPES, "c2")).toBe(false)
    expect(connectionKeepsAnswers(list("kept"), TYPES, null)).toBe(false)
  })
})
