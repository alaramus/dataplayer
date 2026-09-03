import { describe, expect, it } from "vitest"

import type { CatalogNode } from "@/features/catalog/nodes"

import { placesIn } from "./relationPlaces"

const schema = (name: string, system = false): CatalogNode => ({
  kind: "schema",
  id: name,
  name,
  has_children: true,
  is_system: system,
  representations: [],
})

const folder = (name: string): CatalogNode => ({
  kind: "directory",
  id: name,
  name,
  has_children: true,
  representations: [],
})

const file = (name: string): CatalogNode => ({
  kind: "file",
  id: name,
  name,
  has_children: false,
  size_bytes: 4,
  representations: [],
})

describe("where a new relation may go", () => {
  it("offers the groupings of a source that has them", () => {
    const places = placesIn([schema("public"), schema("audit")], "Warehouse")

    expect(places).toEqual([
      { label: "public", value: "public", kind: "schema" },
      { label: "audit", value: "audit", kind: "schema" },
    ])
  })

  it("leaves out a grouping the server owns", () => {
    const places = placesIn([schema("public"), schema("pg_catalog", true)], "Warehouse")

    expect(places.map((place) => place.value)).toEqual(["public"])
  })

  it("offers the folders of a source that keeps files, and its top level", () => {
    const places = placesIn([folder("reports"), file("notes.txt")], "My files")

    // The top level first: it is where a connection to files keeps them, and
    // the empty id is the source's own name for it.
    expect(places).toEqual([
      { label: "My files", value: "", kind: "folder" },
      { label: "reports", value: "reports", kind: "folder" },
    ])
  })

  it("still has somewhere to write when the connection is empty", () => {
    expect(placesIn([], "My files")).toEqual([
      { label: "My files", value: "", kind: "folder" },
    ])
  })

  it("never offers something that is opened rather than filled", () => {
    const places = placesIn([file("a.csv"), folder("kept")], "My files")

    expect(places.map((place) => place.value)).toEqual(["", "kept"])
  })

  it("does not mistake a file with children for a folder", () => {
    // A workbook holds sheets and an archive holds entries, so both are
    // walked into like a folder — and neither can be written a file into.
    const workbook: CatalogNode = {
      kind: "file",
      id: "budget.xlsx",
      name: "budget.xlsx",
      has_children: true,
      size_bytes: 900,
      representations: [],
    }

    const places = placesIn([workbook, folder("reports")], "My files")

    expect(places.map((place) => place.value)).toEqual(["", "reports"])
  })
})
