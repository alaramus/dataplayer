import { describe, expect, it } from "vitest"

import { badgesFor, datasetFacts, foreignKeyLabel } from "./model"
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

describe("datasetFacts", () => {
  it("states what a columnar file knows about itself", () => {
    const facts = datasetFacts({
      kind: "parquet",
      rows: 250,
      row_groups: 3,
      columns: 7,
      compression: ["SNAPPY"],
      created_by: "parquet-cpp-arrow version 25.0.1",
      format_version: "2.6",
      size_bytes: 8812,
    })

    expect(facts.map((fact) => `${fact.label}: ${fact.value}`)).toEqual([
      "Format: Parquet 2.6",
      "Rows: 250",
      "Row groups: 3",
      "Columns: 7",
      "Compression: SNAPPY",
      "Written by: parquet-cpp-arrow version 25.0.1",
      "Size: 8.6 KB",
    ])
  })

  it("leaves out what a file did not say", () => {
    const facts = datasetFacts({
      kind: "parquet",
      rows: 0,
      row_groups: 0,
      columns: 2,
      compression: [],
      created_by: null,
      format_version: "2.6",
      size_bytes: 100,
    })

    expect(facts.map((fact) => fact.label)).toEqual([
      "Format",
      "Rows",
      "Row groups",
      "Columns",
      "Size",
    ])
  })

  it("says where a sheet sits among the others", () => {
    const facts = datasetFacts({
      kind: "worksheet",
      workbook: "budget.xlsx",
      sheet_name: "Working notes",
      sheet_position: 3,
      sheet_count: 3,
      hidden: true,
      rows: 12,
      columns: 4,
    })

    expect(facts.map((fact) => `${fact.label}: ${fact.value}`)).toEqual([
      "Format: Worksheet",
      "Workbook: budget.xlsx",
      "Sheet: Working notes (3 of 3)",
      "Hidden: yes",
      "Rows: 12",
      "Columns: 4",
    ])
  })

  it("says nothing about a sheet being hidden when it is not", () => {
    const facts = datasetFacts({
      kind: "worksheet",
      workbook: "budget.xlsx",
      sheet_name: "Revenue",
      sheet_position: 1,
      sheet_count: 3,
      hidden: false,
      rows: null,
      columns: null,
    })

    expect(facts.map((fact) => fact.label)).toEqual(["Format", "Workbook", "Sheet"])
  })
})
