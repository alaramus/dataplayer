import { describe, expect, it } from "vitest"

import { badgesFor, foreignKeyLabel } from "./model"
import type { RelationModel } from "./model"

const model = {
  node_id: "public.customers",
  schema_name: "public",
  name: "customers",
  kind: "table",
  owner: "postgres",
  persistence: "permanent",
  columns: [],
  constraints: [
    { kind: "primary_key", name: "customers_pkey", columns: ["id"] },
    {
      kind: "foreign_key",
      name: "customers_region_fkey",
      columns: ["region_id", "region_code"],
      target_node_id: "public.regions",
      target_columns: ["id", "code"],
      on_update: "cascade",
      on_delete: "restrict",
      match: "simple",
    },
    {
      kind: "unique",
      name: "customers_name_unique",
      columns: ["name"],
      nulls_not_distinct: false,
    },
  ],
  indexes: [
    {
      name: "customers_name_idx",
      method: "btree",
      unique: false,
      primary: false,
      valid: true,
      columns: ["name"],
      definition: "CREATE INDEX ...",
    },
  ],
  partitioning: null,
  partition_of: null,
} as RelationModel

describe("badgesFor", () => {
  it("marks the column a primary key is made of", () => {
    expect(badgesFor(model, "id").map((badge) => badge.kind)).toEqual(["primary_key"])
  })

  it("marks every column of a composite foreign key", () => {
    expect(badgesFor(model, "region_id").map((badge) => badge.kind)).toEqual(["foreign_key"])
    expect(badgesFor(model, "region_code").map((badge) => badge.kind)).toEqual(["foreign_key"])
  })

  it("gives a column in several constraints a badge for each", () => {
    expect(badgesFor(model, "name").map((badge) => badge.kind)).toEqual(["unique", "index"])
  })

  it("gives an untouched column none", () => {
    expect(badgesFor(model, "balance")).toEqual([])
  })
})

describe("foreignKeyLabel", () => {
  it("names the target and pairs the columns in key order", () => {
    const key = model.constraints?.[1]
    expect(foreignKeyLabel(key as never)).toBe(
      "region_id, region_code → public.regions (id, code)"
    )
  })
})
